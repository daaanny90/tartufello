"""Errori con messaggio pensato per l'utente (in italiano)."""


class FiutoError(Exception):
    """Errore generico della pipeline: il messaggio va mostrato così com'è."""


class ConfigError(FiutoError):
    """Configurazione mancante o incoerente: va sistemata a mano, niente ipotesi."""


class NotConfigured(FiutoError):
    """Sorgente non ancora configurata: il parametro si salta (non è un errore)."""


class ModelError(FiutoError):
    """Il file del modello (model/vth-v1.json) non è come ce lo aspettiamo."""
