import sys
import traceback


def main() -> None:
    try:
        import torch
        from transformers import pipeline

        print("Python:", sys.version.splitlines()[0])
        print("torch:", getattr(torch, "__version__", "not-installed"))
        try:
            print("cuda available:", torch.cuda.is_available())
        except Exception as exc:
            print("cuda check error:", exc)

        print("Initializing HuggingFace pipeline on CPU (device=-1)...")
        classifier = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            device=-1,
            return_all_scores=True,
        )
        print("Pipeline loaded OK. Running sample inference...")
        output = classifier(
            "Apple raises price target after strong quarter",
            truncation=True,
            max_length=512,
        )
        print("Inference output:")
        print(output)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
