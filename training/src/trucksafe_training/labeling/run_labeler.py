"""Orchestrates label generation against the local vLLM endpoint.

TODO: implement once the vLLM service is up. Expected flow:
  1. Walk the image archive (see `trucksafe_training.data.load`).
  2. For each photo, dispatch to vLLM with the category-appropriate prompt
     and the JSON Schema from `shared/schemas/`.
  3. Validate the response against the matching Pydantic model in
     `trucksafe_training.schemas`.
  4. Write JSONL of `{image_path, label}` to `training/data/labels/`.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("labeler is not wired up yet")


if __name__ == "__main__":
    main()
