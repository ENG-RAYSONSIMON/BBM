"""FR-19 delivery channels. In-app works: the Notification row is the
delivery. Email, SMS and WhatsApp are reserved interfaces with no provider
until Phase 5 (FR-23). Using one fails visibly, never pretends to succeed."""

import logging

from .models import Notification

logger = logging.getLogger(__name__)


class ChannelNotConfigured(RuntimeError):
    """The channel has no provider configured, so nothing was sent."""


class Channel:
    code = None

    def send(self, notification, user):
        raise NotImplementedError


class InAppChannel(Channel):
    code = Notification.Channel.IN_APP

    def send(self, notification, user):
        """Nothing to do: the user reads it in the notification centre."""


class ReservedChannel(Channel):
    """An outside channel whose provider isn't wired yet."""

    def __init__(self, code):
        self.code = code

    def send(self, notification, user):
        logger.error(
            "Notification %s not sent: the %s channel has no provider configured.", notification.pk, self.code
        )
        raise ChannelNotConfigured(f"The {self.code} channel has no provider configured.")


CHANNELS = {
    Notification.Channel.IN_APP: InAppChannel(),
    Notification.Channel.EMAIL: ReservedChannel(Notification.Channel.EMAIL),
    Notification.Channel.SMS: ReservedChannel(Notification.Channel.SMS),
    Notification.Channel.WHATSAPP: ReservedChannel(Notification.Channel.WHATSAPP),
}


def deliver(notification, user):
    """Send a notification to one user through its channel. Raises
    ChannelNotConfigured for a channel without a provider."""
    CHANNELS[notification.channel].send(notification, user)
