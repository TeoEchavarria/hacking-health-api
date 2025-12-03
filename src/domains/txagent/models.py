from typing import List, Optional
from pydantic import BaseModel, Field

class TxAgentQuery(BaseModel):
    query: str = Field(..., description="The user's health-related question")
    medical_history: Optional[str] = Field(None, description="Relevant medical history text")
    pdf_summaries: Optional[List[str]] = Field(None, description="Summaries of attached PDF documents")

class Citation(BaseModel):
    source: str
    text: str

class TxAgentResponse(BaseModel):
    reasoning_chain: str = Field(..., description="Step-by-step reasoning from the LLM")
    structured_output: str = Field(..., description="The final answer")
    citations: List[Citation] = Field(default_factory=list)
