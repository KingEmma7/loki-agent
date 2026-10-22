from enum import Enum
from loki.engine.api_chaos import ApiChaosConfig
from loki.personas.base import BasePersona
from loki.personas.adversary import AdversaryPersona
from loki.personas.network_tormentor import NetworkTormentorPersona
from loki.personas.novice_chaotic import NoviceChaoticPersona
from loki.personas.rage_clicker import RageClickerPersona
from loki.personas.swarm import SwarmPersona


class PersonaChoice(str, Enum):
    RAGE_CLICKER = "rage-clicker"
    NOVICE_CHAOTIC = "novice-chaotic"
    NETWORK_TORMENTOR = "network-tormentor"
    ADVERSARY = "adversary"
    SWARM = "swarm"
    ALL = "all"
    NONE = "none"


# Personas that drive the API chaos engine (directly, or through a NetworkTormentor wave).
API_CHAOS_PERSONAS = frozenset({PersonaChoice.SWARM, PersonaChoice.ALL, PersonaChoice.NETWORK_TORMENTOR})


def build_persona(
    choice: PersonaChoice,
    click_burst_count: int = 5,
    api_chaos_config: ApiChaosConfig | None = None,
    seed: int | None = None,
) -> BasePersona | None:
    """Instantiates the persona for a choice. Returns None for NONE (passive observer)."""
    if choice in (PersonaChoice.SWARM, PersonaChoice.ALL):
        return SwarmPersona(click_burst_count=click_burst_count, api_chaos_config=api_chaos_config, seed=seed)
    if choice == PersonaChoice.RAGE_CLICKER:
        return RageClickerPersona(click_burst_count=click_burst_count, seed=seed)
    if choice == PersonaChoice.NOVICE_CHAOTIC:
        return NoviceChaoticPersona(seed=seed)
    if choice == PersonaChoice.NETWORK_TORMENTOR:
        return NetworkTormentorPersona(api_chaos_config=api_chaos_config, seed=seed)
    if choice == PersonaChoice.ADVERSARY:
        return AdversaryPersona(seed=seed)
    return None
