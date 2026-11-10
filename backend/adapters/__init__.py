from common.encryption import decrypt

from adapters.base import UpstreamError
from adapters.domestic.client import DomesticAdapter
from adapters.international.client import InternationalAdapter

FACTORIES = {"cn": DomesticAdapter, "global": InternationalAdapter}


def adapter_for(account):
    factory = FACTORIES.get(account.region)
    if factory is None:
        raise UpstreamError("Unknown region", 422, "INVALID_INPUT")
    return factory(decrypt(bytes(account.credential_encrypted)), account.real_user_id, account.session_id)
