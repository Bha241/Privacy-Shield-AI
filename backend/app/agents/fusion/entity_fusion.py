class EntityFusion:

    def merge(self, regex_entities, llm_entities):

        entities = regex_entities + llm_entities

        remove duplicates

        sort by start

        return entities