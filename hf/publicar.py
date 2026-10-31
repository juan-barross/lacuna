from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
USER = "juan1211"
MODEL_REPO = f"{USER}/lacuna-extrator-qwen2.5-1.5b-lora"
DATASET_REPO = f"{USER}/lacuna-extratos"
SPACE_REPO = f"{USER}/lacuna-extrator"
DATASET_FILES = {
    "README.md": "hf/dataset/README.md",
    "train.jsonl": "data/treino/rotulos_claude.jsonl",
    "dev.jsonl": "data/gold/dev.jsonl",
    "test.jsonl": "data/gold/test.jsonl",
}


def upload(api: HfApi, repo_id: str, repo_type: str, path_in_repo: str, source: str) -> None:
    api.upload_file(
        path_or_fileobj=ROOT / source, path_in_repo=path_in_repo, repo_id=repo_id, repo_type=repo_type
    )


def main() -> None:
    api = HfApi()

    api.create_repo(DATASET_REPO, repo_type="dataset", private=True, exist_ok=True)
    for path_in_repo, source in DATASET_FILES.items():
        upload(api, DATASET_REPO, "dataset", path_in_repo, source)

    upload(api, MODEL_REPO, "model", "README.md", "hf/modelo/README.md")

    api.create_repo(SPACE_REPO, repo_type="space", space_sdk="gradio", private=True, exist_ok=True)
    api.upload_folder(folder_path=ROOT / "hf/space", repo_id=SPACE_REPO, repo_type="space")
    api.add_space_variable(SPACE_REPO, "ADAPTER", MODEL_REPO)

    for kind, repo in [("datasets/", DATASET_REPO), ("", MODEL_REPO), ("spaces/", SPACE_REPO)]:
        print(f"https://huggingface.co/{kind}{repo}")


if __name__ == "__main__":
    main()
