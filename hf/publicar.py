import argparse
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
DATASET_FILES = {
    "train.jsonl": "data/treino/rotulos_claude.jsonl",
    "dev.jsonl": "data/gold/dev.jsonl",
    "test.jsonl": "data/gold/test.jsonl",
}


def card(path: Path, user: str) -> bytes:
    return path.read_text(encoding="utf-8").replace("SEU_USUARIO_HF", user).encode()


def upload(api: HfApi, repo_id: str, repo_type: str, path_in_repo: str, content: bytes | Path) -> None:
    api.upload_file(path_or_fileobj=content, path_in_repo=path_in_repo, repo_id=repo_id, repo_type=repo_type)


def main(user: str) -> None:
    model_repo = f"{user}/lacuna-extrator-qwen2.5-1.5b-lora"
    dataset_repo = f"{user}/lacuna-extratos"
    space_repo = f"{user}/lacuna-extrator"
    api = HfApi()

    api.create_repo(dataset_repo, repo_type="dataset", private=True, exist_ok=True)
    upload(api, dataset_repo, "dataset", "README.md", card(ROOT / "hf/dataset/README.md", user))
    for path_in_repo, source in DATASET_FILES.items():
        upload(api, dataset_repo, "dataset", path_in_repo, ROOT / source)

    upload(api, model_repo, "model", "README.md", card(ROOT / "hf/modelo/README.md", user))

    api.create_repo(space_repo, repo_type="space", space_sdk="gradio", private=True, exist_ok=True)
    api.upload_folder(folder_path=ROOT / "hf/space", repo_id=space_repo, repo_type="space")
    api.add_space_variable(space_repo, "ADAPTER", model_repo)

    for kind, repo in [("datasets/", dataset_repo), ("", model_repo), ("spaces/", space_repo)]:
        print(f"https://huggingface.co/{kind}{repo}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publica dataset, modelo e Space do Lacuna no Hugging Face")
    parser.add_argument("user", help="usuário ou organização no Hugging Face")
    main(parser.parse_args().user)
