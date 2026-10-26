"""The preview hands the writer's article to the portal as the presentation model; it still invents no analysis."""

from django.test import SimpleTestCase

from .reasoning_preview import SAMPLE, present_reasoning


class ReasoningArticleTests(SimpleTestCase):
    def test_article_paragraphs_follow_the_story(self):
        raw = SAMPLE.read_bytes()
        result = present_reasoning(raw)
        for event in result["events"]:
            story = event["reasoning"]
            article = event["article"]
            self.assertNotIn("analysis", event)
            self.assertIsNone(article["photo"])
            self.assertEqual(article["reading_minutes"], story["reading_minutes"])
            self.assertEqual(len(article["paragraphs"]), len(story["article"]))
            claim_ids = {c["id"] for c in story["claims"]}
            for paragraph, block in zip(article["paragraphs"], story["article"]):
                self.assertEqual(paragraph["text"], block["text"])
                self.assertEqual(paragraph["claim_ids"], block["claim_ids"])
                self.assertEqual(
                    paragraph["kind"],
                    "statement" if block["kind"] == "statements" else block["kind"],
                )
                self.assertIn(paragraph["kind"], ("fact", "context", "statement", "not_confirmed"))
                self.assertTrue(set(paragraph["claim_ids"]) <= claim_ids)
