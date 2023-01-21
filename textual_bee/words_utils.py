import random
import string
import timeit
from functools import lru_cache, partial
from typing import Dict, List, Tuple

import httpx

VOWELS = "aeiou"
CONSONANTS = [letter for letter in string.ascii_lowercase if letter not in VOWELS]


def is_letter_selection_good(required: str, optional: List[str]):
    scorebook = get_words_with_letters(
        required=required, optional="".join(optional), min_size=4
    )
    n_words = len(list(scorebook.keys()))
    n_pangrams = len([0 for v in scorebook.values() if v[0] == "Pangram!"])
    print(f"Checking set with {n_words=} and {n_pangrams=}")
    if n_words > 10 and n_pangrams >= 1 and n_words < 100:
        return True

    return False


def randomize_letters() -> Tuple[str, List[str]]:
    for _ in range(1000):
        n_vowels = random.choice([2, 3])
        out = [
            *random.sample(VOWELS, n_vowels),
            *random.sample(CONSONANTS, 7 - n_vowels),
        ]
        random.shuffle(out)
        center = out[0]
        outer = out[1:]
        if is_letter_selection_good(center, outer):
            return center, outer

    return "?", ["?", "?", "?", "?", "?", "?"]


@lru_cache()
def get_popular_words() -> List[str]:
    return (
        httpx.get(
            # # Not a full list:
            # "https://raw.githubusercontent.com/dolph/dictionary/master/popular.txt"
            # # Still not a full list, but better at least:
            "https://raw.githubusercontent.com/lzha97/spelling_bee/master/words.json"
        )
        .json()
        .keys()
    )


def pangram(s):
    return len(set(s.lower())) >= 7


def get_status_from_point_percent(percent: int) -> Tuple[str, int]:
    if percent < 2:
        return "Beginner", 0
    if percent < 5:
        return "Good Start", 1
    if percent < 8:
        return "Moving Up", 2
    if percent < 15:
        return "Good", 3
    if percent < 25:
        return "Solid", 4
    if percent < 40:
        return "Nice", 5
    if percent < 50:
        return "Great", 6
    if percent < 70:
        return "Amazing", 7
    if percent < 100:
        return "Genius", 8
    return "Queen Bee", 8


def get_word_result(word: str) -> Tuple[str, int]:
    if len(word) < 4:
        return "", 0
    if len(word) == 4:
        return "Good!", 1
    if len(word) < 7:
        return "Nice!", len(word)
    if len(set(word)) < 7:
        return "Awesome!", len(word)
    return "Pangram!", len(word) + 7


@lru_cache(maxsize=1024)
def get_words_with_letters(
    required: str, optional: str, min_size: int
) -> Dict[str, Tuple[str, int]]:
    required = required.strip().lower()
    optional = optional.strip().lower()
    all_possible_letters = required + optional
    out = {}
    for word in get_popular_words():
        if len(word) < min_size:
            continue
        if any((letter not in word for letter in required)):
            continue
        if any((letter not in all_possible_letters for letter in word)):
            continue
        out[word] = get_word_result(word)
    return out


if __name__ == "__main__":
    from rich import print

    print(
        timeit.timeit(
            partial(get_words_with_letters, required="B", optional="AILNPT", min_size=4)
        )
    )
    print(
        timeit.timeit(
            partial(get_words_with_letters, required="B", optional="AILNPT", min_size=4)
        )
    )
    print(
        timeit.timeit(
            partial(get_words_with_letters, required="B", optional="AILNPT", min_size=4)
        )
    )
    print(
        timeit.timeit(
            partial(get_words_with_letters, required="B", optional="AILNPT", min_size=4)
        )
    )
    print("labia" in get_popular_words())
    print(get_words_with_letters(required="B", optional="AILNPT", min_size=4))
