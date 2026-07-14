from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import settings


EMBEDDING_DIMENSION = 768

embeddings_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    api_key=settings.gemini_api_key,
    output_dimensionality=EMBEDDING_DIMENSION,
)


def embed_documents(texts: list[str]) -> list[list[float]]:
    return embeddings_model.embed_documents(texts)


def embed_query(text: str) -> list[float]:
    return embeddings_model.embed_query(text)