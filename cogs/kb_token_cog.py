import discord
import random
from discord.ext import commands
from discord.commands import slash_command, Option, SlashCommandGroup
from utils import bot_prefs

# How often a user can claim a token (in seconds)
CLAIM_COOLDOWN = 3600  # 1 hour

# 1 token = 1 second of cooldown modification
SECONDS_PER_TOKEN = 1

class TokenCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("✅ TokenCog loaded!")

    def get_balance(self, user_id: int) -> int:
        """Returns how many tokens the user currently has."""
        return int(bot_prefs.get(f"ktoken_balance_{user_id}", 0))
    
    def set_balance(self, user_id: int, new_balance: int):
        """Set the user's new token balance."""
        bot_prefs.set(f"ktoken_balance_{user_id}", max(new_balance, 0))
    
    def get_claim_cooldown_remaining(self, user_id: int) -> int:
        """Returns how many seconds remain before user can claim again."""
        return int(bot_prefs.get(f"ktoken_claim_cd_{user_id}", 0))

    def set_claim_cooldown(self, user_id: int, seconds: int):
        """Sets the claim cooldown for a user to 'seconds' time-based."""
        bot_prefs.set(f"ktoken_claim_cd_{user_id}", seconds, time_based=True)

    def modify_cooldown(self, cooldown_type: str, target_id: int, delta_seconds: int):
        """
        Modify a user's daily or kringpic cooldown by +/- delta_seconds.
        If negative, it reduces. If positive, it adds.
        """
        # The image cogs store daily cooldown in "daily_img_cd_{user_id}"
        # and kring pic in "kringpic_img_cd_{user_id}"
        if cooldown_type == "daily":
            key = f"daily_img_cd_{target_id}"
        elif cooldown_type == "claim":
            key = f"ktoken_claim_cd_{target_id}"
        else:
            return False  # Unknown type

        current = bot_prefs.get(key, 0)  # how many seconds remain
        new_val = max(0, current + delta_seconds)  # can't go below 0
        # Re-save as time-based so it counts down
        bot_prefs.set(key, new_val, time_based=True)
        return True
    
    ktokengrp = SlashCommandGroup("ktoken", "Base slash command for ktoken commands.")

    ktokengrp_owner = SlashCommandGroup(
        "ktoken_owner",
        "Base slash command for owner related ktoken commands",
        checks=[
            commands.is_owner().predicate
        ],  # Ensures the owner_id user can access this group, and no one else
    )

    @ktokengrp.command(name="claim", description="Claim your ktokens every hour!")
    async def claim(self, ctx: discord.ApplicationContext):
        """Users can claim one token if they're past their cooldown."""
        user_id = ctx.author.id
        remaining = self.get_claim_cooldown_remaining(user_id)
        if remaining > 0:
            # Show the user how long until they can claim again
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            return await ctx.respond(
                f"⏳ You must wait {hours}h {minutes}m {seconds}s before claiming again.", 
                ephemeral=True
            )

        # Award 1 token
        balance = self.get_balance(user_id)
        self.set_balance(user_id, balance + 3600)
        # Set claim cooldown
        self.set_claim_cooldown(user_id, CLAIM_COOLDOWN)

        await ctx.respond(f"✅ You have claimed 1 ktoken! Your new balance: {balance+1}", ephemeral=True)

    @ktokengrp.command(name="balance", description="Check your token balance")
    async def balance(self, ctx: discord.ApplicationContext):
        user_id = ctx.author.id
        bal = self.get_balance(user_id)
        await ctx.respond(f"**{ctx.author.display_name}**: You have **{bal}** ktokens.", ephemeral=True)

    @ktokengrp.command(
        name="spend",
        description="Spend tokens to modify someone's command cooldown"
    )
    async def spend(
        self,
        ctx: discord.ApplicationContext,
        target: Option(discord.Member, description="Who to modify cooldown for"),
        cooldown: Option(str, description="Which cooldown to adjust", choices=["daily", "claim"]),
        tokens: Option(int, description="Number of tokens to spend (≥1) [1 Ktoken = 1 s]", min_value=1),
        mode: Option(str, description="Extend or reduce?", choices=["extend", "reduce"])
    ):
        await ctx.defer()
        """
        Example usage:
        /ktoken spend @gcww daily 3 reduce
        => Reduce gcww's "daily" cooldown by 3 tokens worth of seconds
        """
        user_id = ctx.author.id

        # 1) Check user has enough tokens
        current_balance = self.get_balance(user_id)
        if current_balance < tokens:
            return await ctx.respond(
                f"❌ You only have {current_balance} tokens, but that requires {tokens}.",
                ephemeral=True
            )

        # 2) Convert tokens → seconds
        seconds = tokens * SECONDS_PER_TOKEN
        # If the mode is reduce, we’ll use a negative to reduce the user’s cooldown
        if mode == "reduce":
            seconds = -seconds

        # 3) Modify target's cooldown
        success = self.modify_cooldown(cooldown, target.id, seconds)
        if not success:
            return await ctx.respond("❌ Unknown cooldown type.", ephemeral=True)

        # 4) Deduct tokens from the spender
        self.set_balance(user_id, current_balance - tokens)

        # 5) Notify
        if mode == "reduce":
            verb = "reduced"
            delta_str = f"-{tokens} tokens → {abs(seconds)}s less"
        else:
            verb = "extended"
            delta_str = f"+{tokens} tokens → {seconds}s more"

        await ctx.respond(
            f"✅ {ctx.author.display_name} has {verb} **{target.display_name}**'s **{cooldown}** cooldown.\n"
            f"**Cooldown change:** {delta_str}\n"
            f"**{ctx.author.display_name} current balance:** {current_balance - tokens}"
        )
        
    @ktokengrp_owner.command(
        name="modify",
        description="Change a given users balance of ktokens"
    )
    async def modify(
        self,
        ctx: discord.ApplicationContext,
        target: Option(discord.Member, description="Who to modify balance of"),
        tokens: Option(int, description="number of tokens to add/remove"),
    ):
        user_id = target.id
        current_balance = self.get_balance(user_id)
        new_balance = current_balance + tokens
        # prevent negative final balance
        if new_balance < 0:
            new_balance = 0

        self.set_balance(user_id, new_balance)

        # Decide how you want to phrase it
        verb = "increased" if tokens >= 0 else "decreased"
        abs_tokens = abs(tokens)
        await ctx.respond(
            f"✅ Successfully {verb} **{target.display_name}**'s balance by {abs_tokens} tokens.\n"
            f"**New balance:** {new_balance}",
            ephemeral=True
        )


    #####################
    # Dice Gamble with Higher/Lower + Single Numbers
    #####################
    @ktokengrp.command(name="gamba", description="Bet ktokens on a dice roll, with higher/lower or exact number!")
    async def gamba(
        self,
        ctx: discord.ApplicationContext,
        bet: Option(int, description="How many tokens to bet", min_value=1),
    ):
        """
        /ktoken gamble 10
        => Creates a publicly-visible embed with 8 buttons:
           Higher, Lower, 1, 2, 3, 4, 5, 6.
        => If "Higher" or "Lower" is correct, user wins +bet (1:1).
           If an exact number guess is correct, user wins +2×bet (1:2).
        """
        user_id = ctx.author.id
        current_balance = self.get_balance(user_id)
        if bet > current_balance:
            return await ctx.respond(
                f"❌ You only have {current_balance} tokens, but you tried to bet {bet}.",
                ephemeral=True
            )

        view = DiceBetView(token_cog=self, user_id=user_id, bet_amount=bet)
        embed = discord.Embed(
            title="Dice Gamble!",
            description=(
                f"{ctx.author.mention} is betting **{bet}** tokens.\n"
                "Choose **Higher**, **Lower**, or a specific number 1–6.\n"
                "**Higher** wins if roll is 4–6 (50% chance, 1:1 payout).\n"
                "**Lower** wins if roll is 1–3 (50% chance, 1:1 payout).\n"
                "Exact number wins if you guess it exactly (1/6 chance, 1:5 payout).\n"
                "Mikan will collect your entire bet if you lose."
            ),
            color=discord.Color.blurple()
        )
        await ctx.respond(embed=embed, view=view)

     
    #####################
    # Black Jack with Kringles
    #####################
    @ktokengrp.command(name="blackjack", description="Play blackjack with ktokens!")
    async def blackjack(
    self,
    ctx: discord.ApplicationContext,
    bet: Option(int, description="How many tokens to bet", min_value=1)
    ):
        user_id = ctx.author.id
        current_balance = self.get_balance(user_id)
        if bet > current_balance:
            return await ctx.respond(
                f"❌ You only have {current_balance} tokens, but you tried to bet {bet}.",
                ephemeral=True
            )

        # Deduct the bet up front
        self.set_balance(user_id, current_balance - bet)

        # Start the blackjack game
        view = BlackjackView(self, ctx.author, bet)
        await view.start(ctx)

class DiceBetView(discord.ui.View):
    """
    This view has 8 buttons: Higher, Lower, 1,2,3,4,5,6
    - If user picks Higher (roll in [4,5,6]) => 50% chance => 1:1 payout
    - If user picks Lower  (roll in [1,2,3]) => 50% chance => 1:1 payout
    - If user picks a #    (roll == that # ) => ~16.7% chance => 1:5 payout
    """
    def __init__(self, token_cog, user_id, bet_amount):
        super().__init__(timeout=60)
        self.token_cog = token_cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.chosen = False
        self.message = None

    # Restrict to user
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You're not the one gambling!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if not self.chosen:
            # disable buttons if time runs out
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            # Try updating the message if we have it
            if self.message:
                try:
                    await self.message.edit(content="Bet timed out!", view=self)
                except:
                    pass

    def disable_all_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    async def do_roll(self, guess: str) -> str:
        roll = random.randint(1, 6)
        old_balance = self.token_cog.get_balance(self.user_id)
        # default payout is 0 => user loses bet
        new_balance = max(0, old_balance - self.bet_amount)
        outcome_str = ""

        # Check if guess is "higher" or "lower"
        if guess == "higher" and roll in (4,5,6):
            # 1:1 payout => user gains +bet
            new_balance = old_balance + self.bet_amount
            outcome_str = f"**WIN** +{self.bet_amount}"

        elif guess == "lower" and roll in (1,2,3):
            new_balance = old_balance + self.bet_amount
            outcome_str = f"**WIN** +{self.bet_amount}"

        # Or if guess is a single digit
        elif guess.isdigit():
            chosen_num = int(guess)
            if roll == chosen_num:
                # 1:2 payout => user gains +2×bet
                new_balance = old_balance + (self.bet_amount * 5)
                outcome_str = f"**WIN** +{self.bet_amount * 5}"

        # Then finalize
        self.token_cog.set_balance(self.user_id, new_balance)
        net_change = new_balance - old_balance

        # Format text
        if net_change >= 0:
            msg = (
                f"🎲 Rolled **{roll}**\n"
                f"**Guess**: {guess} => {outcome_str}\n"
                f"**Balance**: {old_balance} → {new_balance}"
            )
        else:
            msg = (
                f"🎲 Rolled **{roll}**\n"
                f"**Guess**: {guess} => You lose your bet!\n"
                f"**Balance**: {old_balance} → {new_balance}"
            )
        return msg

    # Because we have 8 possible buttons, we can do 2 for Higher/Lower, then 6 for digits.
    # Let's put them in 2 rows for readability.

    @discord.ui.button(label="Higher", style=discord.ButtonStyle.primary, row=0)
    async def higher_button(self, button, interaction: discord.Interaction):
        await self.handle_bet(interaction, guess="higher")

    @discord.ui.button(label="Lower", style=discord.ButtonStyle.primary, row=0)
    async def lower_button(self, button, interaction: discord.Interaction):
        await self.handle_bet(interaction, guess="lower")

    @discord.ui.button(label="1", style=discord.ButtonStyle.secondary, row=1)
    async def one_button(self, button, interaction: discord.Interaction):
        await self.handle_bet(interaction, guess="1")

    @discord.ui.button(label="2", style=discord.ButtonStyle.secondary, row=1)
    async def two_button(self, button, interaction: discord.Interaction):
        await self.handle_bet(interaction, guess="2")

    @discord.ui.button(label="3", style=discord.ButtonStyle.secondary, row=1)
    async def three_button(self, button, interaction: discord.Interaction):
        await self.handle_bet(interaction, guess="3")

    @discord.ui.button(label="4", style=discord.ButtonStyle.secondary, row=2)
    async def four_button(self, button, interaction: discord.Interaction):
        await self.handle_bet(interaction, guess="4")

    @discord.ui.button(label="5", style=discord.ButtonStyle.secondary, row=2)
    async def five_button(self, button, interaction: discord.Interaction):
        await self.handle_bet(interaction, guess="5")

    @discord.ui.button(label="6", style=discord.ButtonStyle.secondary, row=2)
    async def six_button(self, button, interaction: discord.Interaction):
        await self.handle_bet(interaction, guess="6")

    async def handle_bet(self, interaction: discord.Interaction, guess: str):
        if self.chosen:
            return await interaction.response.send_message("You've already bet once!", ephemeral=True)
        self.chosen = True

        # Actually do the dice roll
        result = await self.do_roll(guess)
        # disable the other buttons
        self.disable_all_buttons()

        # store the message reference so we can edit if needed
        self.message = interaction.message
        # update the original message
        await interaction.response.edit_message(content=result, embed=None, view=self)
    
class BlackjackView(discord.ui.View):
    def __init__(self, token_cog, player, bet_amount):
        super().__init__(timeout=180)
        self.token_cog = token_cog
        self.player = player
        self.bet = bet_amount

        self.deck = self.generate_deck()
        random.shuffle(self.deck)

        self.player_hands = []  # list of hands
        self.current_hand_index = 0
        self.split_bet = False

        self.dealer_hand = []
        self.message = None
        self.finished = False
        # Keep track of total spent (bet). If the user splits once, 
        # they effectively spend double the initial bet.
        self.total_spent = self.bet  # might become 2× after split

    async def start(self, ctx):
        hand = [self.deck.pop(), self.deck.pop()]
        self.player_hands = [hand]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]

        embed = self.build_embed(initial=True)
        # Save a reference to the interaction's resulting message
        self.message = await ctx.respond(embed=embed, view=self)

    ########################
    # Interaction Restriction
    ########################
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Only the user who started the game can press the buttons;
        everyone else sees an ephemeral error message.
        """
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                "You are not the player of this Blackjack session!",
                ephemeral=True
            )
            return False
        return True

    def generate_deck(self, num_decks=5):
        """Generate num_decks copies of a standard 52-card deck."""
        one_deck = [r + s for r in "23456789TJQKA" for s in "♠♥♦♣"]
        return one_deck * num_decks


    def hand_value(self, hand):
        value, aces = 0, 0
        for card in hand:
            rank = card[0]
            if rank in "JQKT":
                value += 10
            elif rank == "A":
                value += 11
                aces += 1
            else:
                value += int(rank)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def build_embed(self, initial=False, reveal_dealer=False):
        embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.green())

        for i, hand in enumerate(self.player_hands):
            label = "Your hand" if len(self.player_hands) == 1 else f"Hand {i+1}"
            value = self.hand_value(hand)
            marker = "← Playing" if (i == self.current_hand_index and not self.finished) else ""
            embed.add_field(
                name=f"{label} ({value}) {marker}",
                value=", ".join(hand),
                inline=False
            )

        if reveal_dealer or self.finished:
            dval = self.hand_value(self.dealer_hand)
            embed.add_field(
                name=f"Kringbot's hand ({dval})",
                value=", ".join(self.dealer_hand),
                inline=False
            )
        else:
            embed.add_field(
                name="Kringbot's hand (?)",
                value=f"{self.dealer_hand[0]}, ??",
                inline=False
            )

        return embed

    def disable_all_buttons(self):
        for item in self.children:
            item.disabled = True

    def can_split(self):
        return (
            len(self.player_hands) == 1
            and len(self.player_hands[0]) == 2
            and self.player_hands[0][0][0] == self.player_hands[0][1][0]  # same rank
        )

    ########################
    # Main End-Game Logic
    ########################
    async def end_game(self, interaction):
        self.disable_all_buttons()
        self.finished = True

        # Dealer draws to 17
        dealer_val = self.hand_value(self.dealer_hand)
        while dealer_val < 17:
            self.dealer_hand.append(self.deck.pop())
            dealer_val = self.hand_value(self.dealer_hand)

        embed = self.build_embed(reveal_dealer=True)
        total_return = 0
        result_text = ""

        for i, hand in enumerate(self.player_hands):
            pval = self.hand_value(hand)

            # If not split or i==0, bet_amt = self.bet, else another bet
            bet_amt = self.bet if (i == 0 or not self.split_bet) else self.bet
            res = ""
            payout = 0

            if pval > 21:
                # Bust
                res = f"❌ Hand {i+1}: Bust!"
            else:
                # Evaluate vs. dealer
                if dealer_val > 21 or pval > dealer_val:
                    # Possible Blackjack bonus
                    if pval == 21 and len(hand) == 2:
                        # e.g. 1.5 × bet
                        payout = int(bet_amt * 1.5)
                        res = f"🂡 Hand {i+1}: Blackjack! +{payout}"
                    else:
                        payout = bet_amt * 2
                        prof = payout - bet_amt
                        res = f"✅ Hand {i+1}: Win! +{prof}"
                elif pval == dealer_val:
                    # tie => return original bet
                    payout = bet_amt
                    res = f"🤝 Hand {i+1}: Tie! Bet returned."
                else:
                    # dealer higher
                    res = f"❌ Hand {i+1}: Loss."

            total_return += payout
            result_text += res + "\n"

        # 1) Put tokens back
        old_balance = self.token_cog.get_balance(self.player.id)
        self.token_cog.set_balance(self.player.id, old_balance + total_return)

        # 2) Net Change: total_spent is self.bet (and if split, 2× bet).
        # If we split once, total_spent = bet * 2
        net = total_return - self.total_spent
        if net > 0:
            net_str = f"You gained **{net}** tokens overall!"
        elif net < 0:
            net_str = f"You lost **{-net}** tokens overall!"
        else:
            net_str = "You broke even!"

        embed.add_field(name="Results", value=result_text, inline=False)
        embed.add_field(name="Net Change", value=net_str, inline=False)

        await interaction.response.edit_message(embed=embed, view=self)

    ########################
    # Buttons
    ########################
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.success)
    async def hit_button(self, button, interaction: discord.Interaction):
        hand = self.player_hands[self.current_hand_index]
        hand.append(self.deck.pop())

        if self.hand_value(hand) > 21:
            # bust => move to next hand or end
            if self.current_hand_index + 1 < len(self.player_hands):
                self.current_hand_index += 1
            else:
                return await self.end_game(interaction)

        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.danger)
    async def stand_button(self, button, interaction: discord.Interaction):
        # Move to next hand or end
        if self.current_hand_index + 1 < len(self.player_hands):
            self.current_hand_index += 1
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        else:
            await self.end_game(interaction)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.secondary)
    async def split_button(self, button, interaction: discord.Interaction):
        if not self.can_split():
            return await interaction.response.send_message("❌ You can't split this hand.", ephemeral=True)

        current_balance = self.token_cog.get_balance(self.player.id)
        if current_balance < self.bet:
            return await interaction.response.send_message("❌ Not enough tokens to split.", ephemeral=True)

        # Deduct one more bet from player's balance
        self.token_cog.set_balance(self.player.id, current_balance - self.bet)
        self.total_spent += self.bet  # Increase total spent by another bet

        # Perform the split
        first_card = self.player_hands[0][0]
        second_card = self.player_hands[0][1]

        self.player_hands = [
            [first_card, self.deck.pop()],
            [second_card, self.deck.pop()],
        ]
        self.split_bet = True
        self.current_hand_index = 0

        await interaction.response.edit_message(embed=self.build_embed(), view=self)


def setup(bot):
    bot.add_cog(TokenCog(bot))
