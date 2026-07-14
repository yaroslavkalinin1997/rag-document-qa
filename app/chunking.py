from langchain_text_splitters import RecursiveCharacterTextSplitter


text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def split_text(full_text: str) -> list[str]:
    documents = text_splitter.create_documents([full_text])

    return [document.page_content for document in documents]