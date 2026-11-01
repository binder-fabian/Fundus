import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from fundus.accounts.emails import invitation_link, send_invitation
from fundus.accounts.models import Role, User


class Command(BaseCommand):
    help = "Legt einen Administrator an (Ersteinrichtung)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")
        parser.add_argument(
            "--invite",
            action="store_true",
            help="Kein Passwort abfragen, sondern einen Einladungslink erzeugen und mailen.",
        )

    def handle(self, *args, **options):
        email = User.objects.normalize_email(options["email"]).lower()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"Es gibt bereits ein Konto für {email}.")

        user = User(
            email=email,
            first_name=options["first_name"],
            last_name=options["last_name"],
            role=Role.ADMIN,
        )
        if options["invite"]:
            user.set_unusable_password()
            user.save()
            sent = send_invitation(user)
            self.stdout.write(f"Einladungslink für {email}:\n{invitation_link(user)}")
            if not sent:
                self.stderr.write("E-Mail konnte nicht verschickt werden; Link oben verwenden.")
        else:
            password = self._ask_password(user)
            user.set_password(password)
            user.save()

        self.stdout.write(self.style.SUCCESS(f"Administrator {email} angelegt."))
        if User.objects.active_admins().count() < 2:
            self.stdout.write("Hinweis: Empfohlen sind mindestens zwei Administratoren.")

    def _ask_password(self, user):
        while True:
            password = getpass.getpass("Passwort: ")
            if password != getpass.getpass("Passwort wiederholen: "):
                self.stderr.write("Die Passwörter stimmen nicht überein.")
                continue
            try:
                validate_password(password, user)
            except ValidationError as error:
                self.stderr.write(" ".join(error.messages))
                continue
            return password
