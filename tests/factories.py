import factory
from django.utils import timezone

from fundus.accounts.models import Role, User
from fundus.catalog.models import Category, Copy, Location, Title
from fundus.core.models import School, default_school_id
from fundus.loans.models import Loan


class SchoolFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = School

    name = factory.Sequence(lambda n: f"Schule {n}")


def default_school():
    return School.objects.get(pk=default_school_id())


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"lehrkraft{n}@schule.de")
    first_name = "Erika"
    last_name = factory.Sequence(lambda n: f"Muster{n}")
    role = Role.TEACHER
    password = factory.django.Password("geheim-1234")


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    school = factory.LazyFunction(default_school)
    name = factory.Sequence(lambda n: f"Kategorie {n}")
    default_loan_days = 14


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Location

    school = factory.LazyFunction(default_school)
    room = factory.Sequence(lambda n: f"Raum {100 + n}")
    shelf = "Regal 1"


class TitleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Title

    school = factory.LazyFunction(default_school)
    title = factory.Sequence(lambda n: f"Testkoffer {n}")
    author = "Muster, M."
    category = factory.SubFactory(CategoryFactory, school=factory.SelfAttribute("..school"))
    lendable = True


class CopyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Copy

    title = factory.SubFactory(TitleFactory)
    inventory_number = factory.Sequence(lambda n: f"INV-{n:05d}")
    location = factory.SubFactory(LocationFactory)


class LoanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Loan

    copy = factory.SubFactory(CopyFactory)
    borrower = factory.SubFactory(UserFactory)
    status = Loan.Status.LENT
    lent_at = factory.LazyFunction(timezone.now)
    due_date = factory.LazyAttribute(lambda o: o.copy.title.default_due_date())
