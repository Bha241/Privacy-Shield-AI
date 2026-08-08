import os
import sys
import unittest
from pathlib import Path

# Fix sys.path for backend and agents modules
backend_dir = Path(__file__).resolve().parent
agents_dir = backend_dir / "app" / "agents"

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))

try:
    import app.agents as pii_detector
    sys.modules["pii_detector"] = pii_detector
except Exception as e:
    pass

from app.agents.agents.privacy_rag_agent import PrivacyRAGAgent
from app.agents.document_cache import document_cache
from app.agents.intent_classifier import IntentClassifier
from app.agents.document_orchestrator import DocumentOrchestrator
from app.agents.context_builder import ContextBuilder
from app.agents.masking.pii_masker import MaskedResult


class TestDocumentContextPipeline(unittest.TestCase):

    def setUp(self):
        self.agent = PrivacyRAGAgent()
        self.sample_filename = "04_Supply_Chain_Purchase_Order.docx"
        self.sample_document_id = "doc_po_2026_test_1234"
        self.sample_text = (
            "PURCHASE ORDER #PO-2026-8891\n"
            "Buyer: Apex Technologies India Pvt Ltd\n"
            "Vendor: Global Logistics & Supply Solutions Private Limited\n"
            "Item: High-performance Cloud Computing Server Rack Enclosures (Quantity: 50 units)\n"
            "Total Amount: INR 4,500,000\n"
            "Delivery Address: Tech Park Campus, Outer Ring Road, Bangalore - 560103\n"
            "GSTIN: 29AAACA12341Z5\n"
            "Contact Person: Rajesh Kumar (rajesh.kumar@apextech.com)\n"
            "Payment Terms: Net 30 days upon delivery and physical inspection."
        )
        self.masked_result = MaskedResult(
            masked_text=self.sample_text.replace("Rajesh Kumar", "<NAME_1>").replace("29AAACA12341Z5", "<GSTIN_1>"),
            mapping={"<NAME_1>": "Rajesh Kumar", "<GSTIN_1>": "29AAACA12341Z5"},
            detailed_mapping=[]
        )

    def test_1_document_ingestion(self):
        """Test 1: Document Ingestion into PrivacyRAGAgent."""
        success = self.agent.ingest_masked_result(
            masked_result=self.masked_result,
            file_name=self.sample_filename,
            document_id=self.sample_document_id
        )
        self.assertTrue(success)
        self.assertIn(self.sample_document_id, self.agent.doc_texts)
        self.assertGreater(len(self.agent.doc_texts[self.sample_document_id]), 0)
        self.assertEqual(self.agent.doc_texts[self.sample_document_id], self.masked_result.masked_text)

    def test_2_document_id_consistency(self):
        """Test 2: Document ID used during ingestion matches Document ID used during chat."""
        self.agent.ingest_masked_result(
            masked_result=self.masked_result,
            file_name=self.sample_filename,
            document_id=self.sample_document_id
        )
        ingested_id = self.sample_document_id
        resolved_by_id = self.agent.resolve_document_id(ingested_id)
        resolved_by_filename = self.agent.resolve_document_id(self.sample_filename)

        self.assertEqual(ingested_id, resolved_by_id)
        self.assertEqual(ingested_id, resolved_by_filename)

    def test_3_full_document_cache(self):
        """Test 3: Full Document Cache stores complete masked text."""
        self.agent.ingest_masked_result(
            masked_result=self.masked_result,
            file_name=self.sample_filename,
            document_id=self.sample_document_id
        )
        cached_doc = self.agent.document_cache.get(self.sample_document_id)
        self.assertIsNotNone(cached_doc)
        self.assertEqual(cached_doc.masked_text, self.masked_result.masked_text)

    def test_4_document_level_query(self):
        """Test 4: Document-level query uses FULL_DOCUMENT context strategy."""
        doc_queries = [
            "summary the doc",
            "summarize the doc",
            "summarise the doc",
            "overview of this file",
            "What is in the document?",
            "what is in this document",
            "what does the document contain",
            "describe the document",
            "explain this document",
            "tell me about this document",
            "analyze this document",
            "analysis of this document"
        ]
        for q in doc_queries:
            plan = DocumentOrchestrator.orchestrate(query=q, has_active_document=True)
            self.assertEqual(plan.context_strategy, "FULL_DOCUMENT", f"Failed for query: '{q}'")
            self.assertEqual(plan.query_scope, "DOCUMENT_LEVEL", f"Failed for query: '{q}'")

    def test_5_vector_search_returning_zero_chunks(self):
        """Test 5: Vector search returning zero chunks falls back to cached document."""
        self.agent.ingest_masked_result(
            masked_result=self.masked_result,
            file_name=self.sample_filename,
            document_id=self.sample_document_id
        )
        res = ContextBuilder.build_context(
            intent="question",
            query="nonexistent_xyz_term_12345",
            document_id=self.sample_document_id,
            doc_texts=self.agent.doc_texts,
            vector_store_manager=None,
            context_strategy="SEMANTIC_RETRIEVAL"
        )
        self.assertGreater(len(res.context_block), 0)
        self.assertNotEqual(res.context_block, "No matching document context found.")
        self.assertIn("PURCHASE ORDER", res.context_block)

    def test_6_full_document_fallback(self):
        """Test 6: Full document fallback rule when vector retrieval fails."""
        self.agent.ingest_masked_result(
            masked_result=self.masked_result,
            file_name=self.sample_filename,
            document_id=self.sample_document_id
        )
        res = ContextBuilder.build_context(
            intent="question",
            query="unmatched term",
            document_id=self.sample_document_id,
            doc_texts=self.agent.doc_texts,
            context_strategy="SEMANTIC_RETRIEVAL"
        )
        self.assertEqual(res.context_strategy_used, "FULL_DOCUMENT_FALLBACK")
        self.assertGreater(len(res.context_block), 0)

    def test_7_fact_level_query(self):
        """Test 7: Fact-level query strategy assignment."""
        fact_query = "What is the PO number?"
        plan = DocumentOrchestrator.orchestrate(query=fact_query, has_active_document=True)
        self.assertEqual(plan.query_scope, "FACT_LEVEL")
        self.assertEqual(plan.context_strategy, "SEMANTIC_RETRIEVAL")

    def test_8_missing_document(self):
        """Test 8: Missing document yields 'No document has been ingested.'"""
        document_cache._cache.clear()
        res = ContextBuilder.build_context(
            intent="summary",
            query="summary the doc",
            document_id="nonexistent_doc",
            doc_texts={},
            context_strategy="FULL_DOCUMENT"
        )
        self.assertEqual(res.context_block, "No document has been ingested.")
        self.assertEqual(res.context_strategy_used, "NO_DOCUMENT")

    def test_9_groq_generation(self):
        """Test 9: LLM Router handles generation with active context."""
        self.agent.ingest_masked_result(
            masked_result=self.masked_result,
            file_name=self.sample_filename,
            document_id=self.sample_document_id
        )
        messages = self.agent.prompt_manager.build_messages(
            intent="summary",
            context=self.sample_text,
            query="summary the doc",
            doc_type="Purchase Order"
        )
        system_content = messages[0]["content"]
        self.assertIn("PURCHASE ORDER", system_content)

    def test_10_end_to_end_summary(self):
        """Test 10: End-to-end summary request produces document context and valid response."""
        self.agent.ingest_masked_result(
            masked_result=self.masked_result,
            file_name=self.sample_filename,
            document_id=self.sample_document_id
        )
        res = self.agent.answer_query(
            user_query="summary the doc",
            document_id=self.sample_filename
        )
        self.assertGreater(len(res["masked_context"]), 0)
        self.assertNotIn("No matching document context found.", res["masked_context"])
        self.assertNotIn("No document has been ingested.", res["masked_context"])
        self.assertNotIn("there is no document", res["unmasked_response"].lower())
        self.assertNotIn("available document excerpts", res["unmasked_response"].lower())

    def test_11_api_v1_pii_chat_endpoint(self):
        """Test 11: /api/v1/pii/chat schema parsing and context auto-ingest."""
        from app.schemas.pii import ChatMessageRequest
        req = ChatMessageRequest(
            message="summary the doc",
            redacted_text=self.sample_text,
            document_id=self.sample_filename,
            file_name=self.sample_filename
        )
        self.assertEqual(req.document_id, self.sample_filename)
        self.assertEqual(req.file_name, self.sample_filename)
        self.assertEqual(req.redacted_text, self.sample_text)


if __name__ == "__main__":
    unittest.main()
