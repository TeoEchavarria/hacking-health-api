from fastapi import APIRouter, HTTPException
from .models import TxAgentQuery, TxAgentResponse, Citation

router = APIRouter(prefix="/txagent", tags=["TxAgent"])

@router.post("/query", response_model=TxAgentResponse)
async def query_txagent(query: TxAgentQuery):
    """
    Forwards a query to the Harvard TxAgent API (Mocked for now).
    """
    try:
        # TODO: Replace with actual API call to Harvard TxAgent
        # For now, return a mock response
        
        mock_reasoning = (
            "1. Analyzed user query about headaches.\n"
            "2. Reviewed provided medical history (hypertension).\n"
            "3. Consulted medical guidelines for headache management in hypertensive patients.\n"
            "4. Formulated advice based on potential side effects of medication."
        )
        
        mock_output = (
            "Based on your history of hypertension, your headaches might be related to your blood pressure "
            "or a side effect of your medication. It is recommended to monitor your BP closely and consult "
            "your cardiologist before taking NSAIDs like Ibuprofen."
        )
        
        mock_citations = [
            Citation(source="AHA Guidelines 2023", text="Hypertension management guidelines..."),
            Citation(source="MedlinePlus", text="Side effects of common blood pressure medications...")
        ]
        
        return TxAgentResponse(
            reasoning_chain=mock_reasoning,
            structured_output=mock_output,
            citations=mock_citations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
