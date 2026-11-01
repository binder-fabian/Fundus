import pytest

from fundus.accounts.models import User


@pytest.mark.django_db
def test_user_logs_in_with_email():
    user = User.objects.create_user("Anna.Muster@Schule.de", "geheim-1234", first_name="Anna")
    assert user.email == "anna.muster@schule.de"
    assert user.check_password("geheim-1234")
    assert str(user) == "Anna"


@pytest.mark.django_db
def test_create_superuser_sets_flags():
    admin = User.objects.create_superuser("admin@schule.de", "geheim-1234")
    assert admin.is_staff and admin.is_superuser
