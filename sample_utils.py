import re
from collections import Counter
from typing import Iterable


def analyze_word_frequency(
    text: str, stop_words: Iterable[str] | None
) -> list[tuple[str, int]]:
    if text is None:
        raise ValueError("text must not be None")
    if not isinstance(text, str):
        raise TypeError(f"text must be a str, got {type(text).__name__}")

    # Normalize stop words to a set for O(1) membership tests; tolerate None.
    stop_word_set = {word.lower() for word in stop_words} if stop_words else set()

    # Strip any non-word characters (punctuation, quotes, etc.) rather than
    # only "." and ",", so tokens like "development." don't survive.
    words = re.findall(r"[a-z0-9']+", text.lower())

    frequency_map: Counter[str] = Counter(
        word for word in words if word not in stop_word_set
    )

    # Sort by frequency (descending), breaking ties alphabetically for
    # deterministic output.
    sorted_words = sorted(
        frequency_map.items(), key=lambda item: (-item[1], item[0])
    )
    return sorted_words[:3]


def main() -> None:
    sample_article = "Python is great for data science. Python is also amazing for web development. Data science relies heavily on Python, but web development uses Python too."
    ignored_words = ["is", "for", "also", "on", "but", "too"]

    print("Analyzing text frequency...")
    top_three = analyze_word_frequency(sample_article, ignored_words)

    if not top_three:
        print("No frequent words found (input was empty or all stop words).")
        return

    print("Top 3 most frequent words:")
    for word, count in top_three:
        print(f"'{word}': {count} times")


if __name__ == "__main__":
    main()
