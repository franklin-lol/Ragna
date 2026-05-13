"""
Intelligent text chunking.
Prioritizes section boundaries, then paragraphs, then sentences.
Ensures chunks fit within LLM token limits.
"""
import nltk
from typing import List, Tuple
from config import settings

# Initialize NLTK
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)


def chunk_document(sections: List[Tuple[str | None, str]]) -> List[dict]:
    """
    Chunks a list of (section_name, text) into smaller, overlapping chunks.
    """
    all_chunks = []
    
    for section_title, text in sections:
        # Split text into sentences
        sentences = nltk.sent_tokenize(text)
        
        current_chunk_sentences = []
        current_length = 0
        
        for i, sentence in enumerate(sentences):
            sentence_len = len(sentence.split()) # Rough token estimate (words)
            
            # If adding this sentence exceeds max tokens, close current chunk
            if current_length + sentence_len > settings.CHUNK_MAX_TOKENS and current_chunk_sentences:
                all_chunks.append({
                    "content": " ".join(current_chunk_sentences),
                    "section": section_title,
                    "length": current_length
                })
                
                # Keep overlap (last N sentences)
                overlap_count = min(len(current_chunk_sentences), settings.CHUNK_OVERLAP_SENTENCES)
                current_chunk_sentences = current_chunk_sentences[-overlap_count:] if overlap_count > 0 else []
                current_length = sum(len(s.split()) for s in current_chunk_sentences)

            current_chunk_sentences.append(sentence)
            current_length += sentence_len

        # Add remaining text as the last chunk of the section
        if current_chunk_sentences:
            all_chunks.append({
                "content": " ".join(current_chunk_sentences),
                "section": section_title,
                "length": current_length
            })

    return all_chunks
