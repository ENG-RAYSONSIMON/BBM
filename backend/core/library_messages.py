"""Messages from Django, Django REST framework and SimpleJWT that users see.

Listed here only so `makemessages` keeps their Kiswahili text in
locale/sw/LC_MESSAGES/django.po: DRF ships no Kiswahili, and our
LOCALE_PATHS translations take priority over the libraries' own. The text
must match the library source exactly. Nothing imports or calls this.
"""

from django.utils.translation import gettext_noop, ngettext

LIBRARY_MESSAGES = [
    gettext_noop("This field is required."),
    gettext_noop("This field may not be null."),
    gettext_noop("Not a valid string."),
    gettext_noop("This field may not be blank."),
    gettext_noop("Ensure this field has no more than {max_length} characters."),
    gettext_noop("Ensure this field has at least {min_length} characters."),
    gettext_noop("A valid number is required."),
    gettext_noop("Ensure this value is less than or equal to {max_value}."),
    gettext_noop("Ensure this value is greater than or equal to {min_value}."),
    gettext_noop("Ensure that there are no more than {max_digits} digits in total."),
    gettext_noop("Ensure that there are no more than {max_decimal_places} decimal places."),
    gettext_noop("Ensure that there are no more than {max_whole_digits} digits before the decimal point."),
    gettext_noop("A valid integer is required."),
    gettext_noop("Date has wrong format. Use one of these formats instead: {format}."),
    gettext_noop("Enter a valid email address."),
    gettext_noop("Must be a valid UUID."),
    gettext_noop("No file was submitted."),
    gettext_noop("The submitted data was not a file. Check the encoding type on the form."),
    gettext_noop("The submitted file is empty."),
    gettext_noop("Must be a valid boolean."),
    gettext_noop('"{input}" is not a valid choice.'),
    gettext_noop('Invalid pk "{pk_value}" - object does not exist.'),
    gettext_noop("This list may not be empty."),
    gettext_noop("Not found."),
    gettext_noop("You do not have permission to perform this action."),
    gettext_noop("Authentication credentials were not provided."),
    gettext_noop("Incorrect authentication credentials."),
    gettext_noop('Method "{method}" not allowed.'),
    gettext_noop("Malformed request."),
    gettext_noop("Request was throttled."),
    gettext_noop("Token is invalid or expired"),
    gettext_noop("This password is too common."),
    gettext_noop("This password is entirely numeric."),
    gettext_noop("The password is too similar to the %(verbose_name)s."),
]


def _plural_messages(n):  # pragma: no cover - read by makemessages only
    return [
        ngettext(
            "This password is too short. It must contain at least %(min_length)d character.",
            "This password is too short. It must contain at least %(min_length)d characters.",
            n,
        ),
        ngettext("Expected available in {wait} second.", "Expected available in {wait} seconds.", n),
    ]
