from __future__ import annotations

import itertools
import random
from functools import partial
import string
from typing import List, Literal, Optional, Tuple
import click

from rich import color as rich_color
from textual import events
from textual.app import App, ComposeResult
from textual.color import Color
from textual.containers import Container, Horizontal, Vertical
from textual.geometry import Spacing
from textual.reactive import Reactive, var
from textual.widgets import Button, Footer, Static

from .words_utils import (
    get_status_from_point_percent,
    get_words_with_letters,
    pangram,
    randomize_letters,
)


def rich_highlight(s):
    return f"[on #f3da25]{s}[/on #f3da25]"


def style_if_pangram(w: str):
    if pangram(w):
        return rich_highlight(w)
    return w


def columnify(list_of_words: List[str], col_size: int):
    columns = []

    remaining = list_of_words.copy()
    while len(remaining) > 0:
        current_col = []
        for _ in range(col_size):
            if len(remaining) == 0:
                break
            current_col.append(remaining.pop())
        columns.append(current_col)
    return columns


BLACK_COLOR = rich_color.Color.from_triplet(rich_color.parse_rgb_hex("000000"))
YELLOW_COLOR = rich_color.Color.from_triplet(rich_color.parse_rgb_hex("f3da25"))
OTHER_YELLOW = "#f8dc24"


class Splash(Vertical):
    def compose(self):
        yield Static(":Honeybee:", classes="splash-part title first")
        yield Static("Textual Bee", classes="splash-part title")
        yield Static("How many words can you", classes="splash-part subtitle first")
        yield Static("make with 7 letters?", classes="splash-part subtitle second")
        yield Button("Play", id="play")


class Status(Horizontal):
    def compose(self) -> ComposeResult:
        yield Static("", id="status-string")
        yield Static("", id="point-progress-bar")


class BeeBoard(Static):
    def compose(self) -> ComposeResult:
        yield Static("-", classes="hive-placeholder")
        yield Button("-", id="letter-top", classes="hive-outer")
        yield Static("-", classes="hive-placeholder")
        yield Button("-", id="letter-top-left", classes="hive-outer")
        yield Button("-", id="letter-top-right", classes="hive-outer")
        yield Button("-", id="letter-center", classes="hive-inner")

        yield Button("-", id="letter-bottom-left", classes="hive-outer")
        yield Button("-", id="letter-bottom-right", classes="hive-outer")

        yield Button("-", id="letter-bottom", classes="hive-outer")
        yield Static("-", classes="hive-placeholder")
        yield Static("-", classes="hive-placeholder")


class Controls(Horizontal):
    def compose(self) -> ComposeResult:
        yield Button("Delete", id="delete", classes="controls")
        yield Button("↻", id="shuffle", classes="controls")
        yield Button("Enter", id="enter", classes="controls")


class BeeApp(App):
    CSS_PATH = "app.css"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+r", "reset_game", "Reset"),
        ("tab", "null", "Found words"),
        ("spacebar", "action_shuffle_letters", "Shuffle"),
        ("→", "null", "Next page (found words)"),
    ]

    # Animation variables
    outer_opacity = Reactive.init(1.0)
    feedback_opacity = Reactive.init(0.0)
    splash_opacity = Reactive.init(1.0)

    total_points = var(0)
    current_points = var(0)
    current_guess = var("")
    center_letter = var("")
    outer_letters = var(("", "", "", "", "", ""))
    already_found_words = var(tuple)
    feedback = var(("", 0))

    cursor = ""
    cursor_balancer = ""
    stylized_guess = ""

    found_word_column_dims = var(tuple)
    target_page = var(0)
    current_page = var(0.0)

    starting_letters: None | str = None
    simplified = False

    @property
    def recent_words_open(self):
        return self.query_one("#recent-words", Button).has_class("full-recent-words")

    @property
    def main_visible(self):
        return self.query_one("#main").styles.display == "block"

    def action_null(self):
        ...

    def on_mount(self):
        self.set_interval(1.0, self.blink_cursor_on)
        for e in self.query(Button).results():
            e.can_focus = False
            e.ACTIVE_EFFECT_DURATION = 0.1  # type: ignore
            if not self.simplified:
                e.add_class("fancy")
        self.action_reset_game(self.starting_letters)

    def compose(self) -> ComposeResult:
        """Add our buttons."""
        yield Footer()
        yield Splash(id="splash")
        yield Container(
            Status(id="status-bar"),
            Button("", id="recent-words"),
            Static("", id="feedback"),
            Static("", id="current-letters"),
            BeeBoard(id="board"),
            Controls(id="controls-bar"),
            id="main",
        )

    def action_reset_game(self, letters: Optional[str] = None):
        if letters is None:
            self.center_letter, self.outer_letters = randomize_letters()
        else:
            self.center_letter = letters[0]
            self.outer_letters = [letter for letter in letters[1:]]

        self.scorebook = get_words_with_letters(
            required=self.center_letter,
            optional="".join(self.outer_letters),
            min_size=4,
        )
        print(self.scorebook)
        self.already_found_words = tuple()
        self.total_points = sum((p[1] for p in self.scorebook.values()))
        self.current_points = 0
        self.current_guess = ""
        self.query_one("#main").styles.display = "none"
        self.query_one("#splash").styles.display = "block"
        self.splash_opacity = 1.0

    def action_shuffle_letters(self):
        shuffled = [letter.upper() for letter in self.outer_letters]
        random.shuffle(shuffled)
        self.query_one("#letter-top", Button).label = shuffled[0]
        self.query_one("#letter-top-left", Button).label = shuffled[1]
        self.query_one("#letter-top-right", Button).label = shuffled[2]
        self.query_one("#letter-bottom-left", Button).label = shuffled[3]
        self.query_one("#letter-bottom-right", Button).label = shuffled[4]
        self.query_one("#letter-bottom", Button).label = shuffled[5]

    def action_scroll_left(self):
        if self.recent_words_open and self.target_page > 0:
            self.target_page = self.target_page - 1

    def action_scroll_right(self):
        columns_required = -(
            len(self.already_found_words) // -max(self.found_word_column_dims[1], 1)
        )
        pages_required = -(columns_required // -2)
        if self.recent_words_open and self.target_page < pages_required - 1:
            self.target_page = self.target_page + 1

    def submit_guess(self):
        self.feedback = "", 0
        if len(self.current_guess) < 4:
            self.feedback = "Too short", 0
        elif self.current_guess.lower() in self.already_found_words:
            self.feedback = "Already found", 0
        elif self.center_letter.lower() not in self.current_guess.lower():
            self.feedback = "Missing center letter", 0
        elif self.current_guess.lower() not in self.scorebook.keys():
            self.feedback = "Not in word list", 0
        else:
            feedback_str, points = self.scorebook[self.current_guess.lower()]
            self.current_points = self.current_points + points
            self.already_found_words = (
                self.current_guess.lower(),
                *self.already_found_words,
            )
            self.feedback = feedback_str, points

        self.current_guess = ""

    def watch_center_letter(self, center_letter: str):
        # self.action_reset_game()
        self.query_one("#letter-center", Button).label = center_letter.upper()

    def watch_outer_letters(self, outer_letters: str):
        assert len(outer_letters) == 6
        # self.action_reset_game()
        self.action_shuffle_letters()

    def watch_outer_opacity(self, outer_opacity: float):
        for id in (
            "top",
            "top-left",
            "top-right",
            "bottom-left",
            "bottom-right",
            "bottom",
        ):
            self.query_one(f"#letter-{id}", Button).styles.text_opacity = outer_opacity

    def watch_feedback_opacity(self, feedback_opacity: float):
        self.query_one("#feedback", Static).styles.opacity = feedback_opacity

    def watch_splash_opacity(self, splash_opacity: float):
        self.query_one("#splash", Splash).styles.opacity = splash_opacity
        for e in self.query(".splash-part").results():
            e.styles.opacity = splash_opacity
        self.query_one("#play", Button).styles.background = Color.from_rich_color(
            YELLOW_COLOR
        ).lighten(1 - splash_opacity)
        self.query_one("#play", Button).styles.text_opacity = splash_opacity

    def update_guess_display(self):
        self.query_one("#current-letters", Static).update(
            self.cursor_balancer + self.stylized_guess + self.cursor
        )

    def watch_current_guess(self, current_guess: str):
        self.stylized_guess = "".join(
            (
                f"[#f3da25]{letter}[/#f3da25]"
                if letter.upper() == self.center_letter.upper()
                else letter
                for letter in current_guess
            )
        )
        self.update_guess_display()

    def blink_cursor_on(self):
        self.cursor = "[#f3da25]⎸[/#f3da25]"
        self.cursor_balancer = " "
        self.update_guess_display()
        self.set_timer(0.5, self.blink_cursor_off)

    def blink_cursor_off(self):
        self.cursor = ""
        self.cursor_balancer = ""
        self.update_guess_display()

    def watch_already_found_words(self, already_found_words: Tuple[str]):
        if len(already_found_words) == 0:
            self.query_one("#recent-words", Button).label = ""
            return
        previous_result = "   ".join(
            (style_if_pangram(w.capitalize()) for w in already_found_words[1:])
        )
        new = already_found_words[0].capitalize() + "   "
        self.query_one("#recent-words", Button).label = previous_result

        def a_little_more(counter):
            current_tape = new[-counter:]

            if pangram(already_found_words[0]):
                before, after = current_tape.split(" ", maxsplit=1)
                before = rich_highlight(before)
                current_tape = before + " " + after

            self.query_one("#recent-words", Button).label = (
                current_tape + previous_result
            )
            if counter < len(new):
                self.set_timer(0.01, partial(a_little_more, counter + 1))

        self.set_timer(0.01, partial(a_little_more, 1))

    def update_found_word_page(self):
        if (
            len(self.found_word_column_dims) != 2
            or not self.recent_words_open
            or self.found_word_column_dims[1] <= 0
        ):
            return
        summary = f"You have found {len(self.already_found_words)} words\n\n"

        columns = columnify(
            [w.capitalize() for w in sorted(self.already_found_words, reverse=True)],
            self.found_word_column_dims[1],
        )

        for parts in itertools.zip_longest(*columns):
            col_width = self.found_word_column_dims[0]
            current_row = " " + " ".join(
                (s[:col_width].ljust(col_width) for s in parts if isinstance(s, str))
            )
            current_divider = " " + " ".join(
                ("─" * col_width for _ in parts if isinstance(_, str))
            )

            start = round(self.current_page * (self.found_word_column_dims[0] * 2 + 2))
            length = self.found_word_column_dims[0] * 2 + 2  # + 2?

            summary += (
                "\n".join(
                    [
                        " ".join(
                            style_if_pangram(w)
                            for w in current_row[start : start + length].split(" ")
                        ),
                        "[#dedede]"
                        + current_divider[start : start + length]
                        + "[/#dedede]",
                    ]
                )
                + "\n"
            )

        n_pages = -(len(columns) // -2)
        if n_pages > 1:
            # Show paginator
            summary += (
                (
                    " ".join(
                        [
                            *(["1"] * round(self.current_page)),
                            "2",
                            *(["1"] * (n_pages - round(self.current_page) - 1)),
                        ]
                    )
                )
                .center(self.found_word_column_dims[0] * 2 + 4)
                .replace("1", "[#dedede]●[/#dedede]")
                .replace("2", "[#121212]●[/#121212]")
            )

        self.query_one("#recent-words", Button).label = summary

    def watch_target_page(self, target_page):
        self.animate("current_page", target_page, duration=0.3)

    def watch_current_page(self, current_page: float):
        self.update_found_word_page()

    def watch_found_word_column_dims(self, found_word_column_dims: tuple):
        self.update_found_word_page()

    def set_feedback_class(self, colorname: Literal["black", "white"]):
        self.query_one("#feedback", Static).remove_class("feedback-black")
        self.query_one("#feedback", Static).remove_class("feedback-white")
        self.query_one("#feedback", Static).add_class(f"feedback-{colorname}")

    def watch_feedback(self, feedback: Tuple[str, int]):
        feedback_string, points = feedback
        self.set_feedback_class("white")
        if feedback_string == "":
            return

        pad = 2
        if points == 0:
            self.set_feedback_class("black")
            self.query_one("#feedback", Static).update(f" {feedback_string} ")
        else:
            points_str = f"+{points}"
            styled_feedback = (
                f"[on #f8dc24] {feedback_string} [/on #f8dc24]"
                if feedback_string == "Pangram!"
                else f" [underline]{feedback_string}[/underline] "
            )
            self.query_one("#feedback", Static).update(
                " " * len(points_str) + f" {styled_feedback} " + points_str
            )
            pad = (len(points_str) * 2) + 4
        self.query_one("#feedback", Static).styles.width = len(feedback_string) + pad
        self.update_widget_size("feedback")
        self.animate(
            "feedback_opacity",
            1.0,
            duration=0.3,
        )

        def bring_back():
            self.animate(
                "feedback_opacity",
                0.0,
                duration=0.3,
            )

        self.set_timer(1.0, bring_back)

    def watch_current_points(self, current_points: int):
        name, rank = get_status_from_point_percent(
            round(
                100
                * current_points
                / (self.total_points if self.total_points > 0 else 1)
            )
        )
        self.query_one("#status-string", Static).update(f"[bold]{name}[/bold]")
        points_str = str(current_points)
        before = "[#dedede]──[/#dedede]".join(["[#f3da25]●[/#f3da25]"] * rank) + (
            "[#dedede]─[/#dedede]" if rank > 0 else ""
        )
        after = (
            "[#dedede]─[/#dedede]" if (9 - rank - 1) > 0 else ""
        ) + "[#dedede]──[/#dedede]".join(["[#dedede]●[/#dedede]"] * (9 - rank - 1))
        self.query_one("#point-progress-bar", Static).update(
            before
            + "[#f3da25]([/#f3da25]"
            + f"[on #f3da25]{points_str}[/on #f3da25]"
            + "[#f3da25])[/#f3da25]"
            + after
        )

    def try_press_letter(self, letter: str):
        for id in (
            "top",
            "top-left",
            "top-right",
            "bottom-left",
            "bottom-right",
            "bottom",
            "center",
        ):
            button = self.query_one(f"#letter-{id}", Button)
            if button.label.plain == letter.upper():  # type: ignore
                button.press()

    def on_key(self, event: events.Key) -> None:
        """Called when the user presses a key."""
        if self.main_visible:
            if event.key == "tab":
                self.query_one("#recent-words", Button).press()
            if not self.recent_words_open:
                if event.key in [
                    self.center_letter.lower(),
                    *(letter.lower() for letter in self.outer_letters),
                ]:
                    self.try_press_letter(event.key)
                elif event.key == "backspace":
                    self.query_one("#delete", Button).press()
                elif event.key == "enter":
                    self.query_one("#enter", Button).press()
                elif event.key == "space":
                    self.query_one("#shuffle", Button).press()
        else:
            if event.key == "enter" or event.key == "space":
                self.query_one("#play", Button).press()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Called when a button is pressed."""

        button_id = event.button.id
        assert button_id is not None

        if button_id.startswith("letter-"):
            self.current_guess = self.current_guess + str(
                self.query_one(f"#{button_id}", Button).label
            )
        elif button_id == "delete":
            self.current_guess = self.current_guess[:-1]
        elif button_id == "shuffle":
            self.animate(
                "outer_opacity",
                0.0,
                duration=0.3,
            )

            def bring_back():
                self.action_shuffle_letters()
                self.animate(
                    "outer_opacity",
                    1.0,
                    duration=0.3,
                )

            self.set_timer(0.3, bring_back)
        elif button_id == "enter":
            self.submit_guess()
        elif button_id == "play":
            self.update_column_dims()
            self.animate(
                "splash_opacity",
                0.0,
                duration=0.4,
            )

            def show():
                self.query_one("#splash").styles.display = "none"
                self.query_one("#main").styles.display = "block"

            self.set_timer(0.4, show)
        elif button_id == "recent-words":
            self.update_column_dims()
            self.query_one("#recent-words", Button).toggle_class("full-recent-words")
            for id in ("feedback", "current-letters", "board", "controls-bar"):
                self.query_one(f"#{id}").toggle_class("hide")

            if self.recent_words_open:
                self.update_found_word_page()
            else:
                self.watch_already_found_words(self.already_found_words)  # type: ignore

    def on_resize(self, _: events.Resize):
        self.update_widget_size("feedback")
        self.update_widget_size("board")
        self.update_widget_size("controls-bar")
        self.update_widget_size("play")
        self.update_column_dims()
        self.current_page = 0
        self.target_page = 0

    def update_column_dims(self):
        self.found_word_column_dims = tuple()
        self.found_word_column_dims = (
            round(self.query_one("#recent-words", Button).size.width / 2) - 2,
            (self.query_one("#main").size.height // 2) - 3,
        )

    def update_widget_size(self, id: str):
        feedback_style = self.query_one(f"#{id}").styles
        feedback_style.margin = Spacing.horizontal(
            (self.size.width - int(feedback_style.width.value)) // 2  # type: ignore
        )


def validate_letters(ctx, param, value):
    if value is None or (
        isinstance(value, str)
        and len(value) == 7
        and all((letter.lower() in string.ascii_lowercase for letter in value))
    ):
        return value
    raise click.BadParameter("Must be 7 letters")


@click.command()
@click.option(
    "--letters",
    default=None,
    type=click.UNPROCESSED,
    callback=validate_letters,
    help="The letters to use for the board. "
    "The first letter will be the center letter. "
    "Leave blank to generate randomly.",
)
@click.option(
    "--answers",
    is_flag=True,
    help="Don't run the game, just print out "
    "the answers to the set of letters provided by --letters.",
)
@click.option(
    "--simplified",
    is_flag=True,
    help="Run the game with simplified graphics (for asciinema, for example)",
)
def run_app(letters: Optional[str], answers: bool, simplified: bool):
    if answers:
        if letters is None:
            raise click.BadParameter("Answers must include --letters as well.")
        from rich import print

        print(get_words_with_letters(letters[0], letters[1:], 4))

    else:
        app = BeeApp()
        app.starting_letters = letters
        app.simplified = simplified
        app.run()


if __name__ == "__main__":
    run_app()
