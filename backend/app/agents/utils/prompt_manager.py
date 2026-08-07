from pii_detector.prompts.pii_extraction import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
)


class PromptManager:

    @staticmethod
    def build_pii_prompt(text: str, max_entities: int = 8, compact: bool = True):
        """
        Build the prompts for the LLM. Allows passing max_entities and whether to
        request the compact array format.
        """

        # customize user template with max_entities if needed
        user_text = USER_TEMPLATE.format(text=text)
        if max_entities != 8:
            user_text = user_text + f"\n\nReturn at most {max_entities} entities."

        return [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_text,
            },
        ]
