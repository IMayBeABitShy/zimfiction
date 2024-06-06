"""
An L{zimfiction.implication.finder.ImplicationFinder} for extracting characters from relationships.
"""
from .finder import ImplicationFinder


class RelationshipCharactersFinder(ImplicationFinder):
    """
    An ImplicationFinder extracting characters from relationships.
    """
    def get_implied_tags(self, story, implied_tags):
        relationships = []
        # add relationships from other implication finders
        for implied_tag in implied_tags:
            if implied_tag[0] == "relationship":
                relationships.append(implied_tag[1])
        # add relationships from story
        for relationship in story.relationships:
            relationships.append(relationship.name)
        # split relationships
        characters = []
        for relationship in relationships:
            for sep in ("/", "&"):
                if sep not in relationship:
                    continue
                for character in relationship.split(sep):
                    characters.append(character.strip())
        return [("character", c) for c in characters]
