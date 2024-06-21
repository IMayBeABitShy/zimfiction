"""
An L{zimfiction.implication.finder.ImplicationFinder} for extracting
characters and sub-relationships from relationships.

A relationship A/B/C will imply:
    - characters A, B and C
    - relationships A/B, B/C and A/C
"""
import itertools

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
        subrelationships = []
        for relationship in relationships:
            for sep in ("/", "&"):
                if sep not in relationship:
                    continue
                for character in relationship.split(sep):
                    characters.append(character.strip())
                if relationship.count(sep) >= 2:
                    # has subrelationships
                    splitted_relationship = relationship.split(sep)
                    for sr in itertools.combinations(splitted_relationship, 2):
                        subrelationships.append(sep.join(sr))
        implied_tags = [("character", c) for c in characters] + [("relationship", sr) for sr in subrelationships]
        return implied_tags
