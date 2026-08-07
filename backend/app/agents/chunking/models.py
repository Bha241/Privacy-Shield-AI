from dataclasses import dataclass


@dataclass
class TextChunk:
    text: str
    start_offset: int
    end_offset: int
    chunk_id: int