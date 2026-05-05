from app.models import CardioTraceContext
from typing import Protocol
from app.exceptions import FrameParsingError


class FrameParser(Protocol):
    def parse(self, context: CardioTraceContext) -> CardioTraceContext: ...
    def parsing_applicable(self, context: CardioTraceContext) -> bool: ...


class ParsersChain:
    def __init__(self):
        self.parsers = []
        # self.add_parser(AppleParser())
        # self.add_parser(GarminParser())

    def add_parser(self, parser: FrameParser) -> None:
        self.parsers.append(parser)

    def parse(self, context: CardioTraceContext) -> CardioTraceContext:
        parsers_votes = [parser.parsing_applicable(context) for parser in self.parsers]
        votes_sum = sum(parsers_votes)
        if votes_sum == 0:
            raise FrameParsingError("No parser found for the given context")
        if votes_sum > 1:
            raise FrameParsingError("Multiple parsers found for the given context")
        return self.parsers[parsers_votes.index(True)].parse(context)
