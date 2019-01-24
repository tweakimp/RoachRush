from .data import PlayerType, Race, Difficulty
from .bot_ai import BotAI


class AbstractPlayer:
    def __init__(self, p_type, race=None, difficulty=None):
        assert isinstance(p_type, PlayerType)

        if p_type == PlayerType.Computer:
            assert isinstance(difficulty, Difficulty)

        elif p_type == PlayerType.Observer:
            assert race is None
            assert difficulty is None

        else:
            assert isinstance(race, Race)
            assert difficulty is None

        self.type = p_type
        if race is not None:
            self.race = race
        if p_type == PlayerType.Computer:
            self.difficulty = difficulty


class Human(AbstractPlayer):
    def __init__(self, race):
        super().__init__(PlayerType.Participant, race)

    def __str__(self):
        return f"Human({self.race._name_})"


class Bot(AbstractPlayer):
    def __init__(self, race, ai):
        """
        AI can be None if this player object is just used to inform the
        server about player types.
        """
        assert isinstance(ai, BotAI) or ai is None, f"{ai, type(ai)}"
        super().__init__(PlayerType.Participant, race)
        self.ai = ai

    def __str__(self):
        return f"Bot {self.ai.__class__.__name__}({self.race._name_})"


class Computer(AbstractPlayer):
    def __init__(self, race, difficulty=Difficulty.Easy):
        super().__init__(PlayerType.Computer, race, difficulty)

    def __str__(self):
        return f"Computer {self.difficulty._name_}({self.race._name_})"


class Observer(AbstractPlayer):
    def __init__(self):
        super().__init__(PlayerType.Observer)

    def __str__(self):
        return f"Observer"


class Player(AbstractPlayer):
    @classmethod
    def from_proto(cls, proto):
        if PlayerType(proto.type) == PlayerType.Observer:
            return cls(proto.player_id, PlayerType(proto.type), None, None, None)
        return cls(
            proto.player_id,
            PlayerType(proto.type),
            Race(proto.race_requested),
            Difficulty(proto.difficulty) if proto.HasField("difficulty") else None,
            Race(proto.race_actual) if proto.HasField("race_actual") else None,
        )

    def __init__(self, player_id, type, requested_race, difficulty=None, actual_race=None):
        super().__init__(type, requested_race, difficulty)
        self.id: int = player_id
        self.actual_race: Race = actual_race
