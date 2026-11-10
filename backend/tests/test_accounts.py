import pytest

from apps.accounts.models import Account, AccountGroup
from common.encryption import encrypt
from common.problems import ApiProblem
from services.account_service import create_account, import_accounts


@pytest.mark.django_db
def test_regions_never_share_an_identifier():
    body = {"name": "同名", "identifier": "same@example.com", "credential": "tok"}
    create_account({**body, "region": "cn"})
    create_account({**body, "region": "global"})
    with pytest.raises(ApiProblem) as caught:
        create_account({**body, "region": "cn"})
    assert caught.value.code == "CONFLICT"


@pytest.mark.django_db
def test_group_cannot_cross_regions():
    group = AccountGroup.objects.create(region="cn", name="国内组")
    with pytest.raises(ApiProblem):
        create_account({
            "region": "global", "name": "g", "identifier": "g@example.com",
            "credential": "tok", "group_id": group.id,
        })


@pytest.mark.django_db
def test_import_stays_inside_its_region():
    created, failed = import_accounts("cn", [
        {"name": "a", "identifier": "a@example.com", "credential": "tok"},
        {"name": "", "identifier": "b@example.com", "credential": "tok"},
    ])
    assert len(created) == 1 and created[0].region == "cn"
    assert failed and Account.objects.filter(region="global").count() == 0


@pytest.mark.django_db
def test_list_requires_a_region_and_filters_by_it(client):
    Account.objects.create(region="cn", name="c", identifier="c@example.com", credential_encrypted=encrypt("t"))
    Account.objects.create(region="global", name="g", identifier="g@example.com", credential_encrypted=encrypt("t"))
    refused = client.get("/api/v1/accounts")
    assert refused.status_code == 422
    listed = client.get("/api/v1/accounts?region=cn")
    assert listed.status_code == 200
    assert [row["region"] for row in listed.json()["data"]["items"]] == ["cn"]
    assert "credential" not in listed.json()["data"]["items"][0]


@pytest.mark.django_db
def test_admin_endpoints_reject_missing_and_wrong_tokens(client):
    anonymous = client.__class__()
    assert anonymous.get("/api/v1/accounts?region=cn").status_code == 403
    anonymous.credentials(HTTP_AUTHORIZATION="Bearer wrong")
    assert anonymous.get("/api/v1/accounts?region=cn").status_code == 403
