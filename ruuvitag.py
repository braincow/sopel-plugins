from sopel import module
from sopel.config.types import StaticSection, ValidatedAttribute
import json
import requests
import google.auth.transport.requests
from google.oauth2.service_account import IDTokenCredentials


class RuuvitagError(Exception):
    pass


class RuuvitagSection(StaticSection):
    sa_json = ValidatedAttribute('sa_json', str)
    endpoint = ValidatedAttribute('endpoint', str)


def setup(bot):
    bot.config.define_section('ruuvitag', RuuvitagSection)


def configure(config):
    config.define_section('ruuvitag', RuuvitagSection, validate=False)
    config.ruuvitag.configure_setting(
            'sa_json',
            ('Where is the GCP service account key file '
                'located at (aka filename)?'))
    config.ruuvitag.configure_setting(
            'endpoint',
            'What is the GCP cloud function endpoint URL to call?')


def invoke_endpoint(url, id_token):
    headers = {'Authorization': 'Bearer ' + id_token}

    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        raise RuuvitagError(
                ("Calling API endpoint failed with "
                    "HTTP status code: {}").format(r.status_code))

    return r.content.decode('utf-8')


def format_output(name, data):
    return "At '{}' it is currently: {}C".format(
            name,
            data["temperature"]
            )


@module.commands('ruuvitag')
@module.rate(user=60, channel=60, server=1)
def ruuvitag(bot, trigger):
    """Displays last recorded Bluetooth beacon value
    (if available) for a requested Ruuvi tag or if not
    specified for all known ones."""
    credentials = IDTokenCredentials.from_service_account_file(
        bot.config.ruuvitag.sa_json,
        target_audience=bot.config.ruuvitag.endpoint)

    request = google.auth.transport.requests.Request()
    credentials.refresh(request)

    response = invoke_endpoint(bot.config.ruuvitag.endpoint, credentials.token)

    tags = dict()
    for tag in json.loads(response):
        tags[tag["name"]] = tag["data"]

    if len(tags) == 0:
        bot.say("No latest tag information available.")
        return

    if trigger.group(2) is not None:
        if trigger.group(2) not in tags:
            bot.say("I dont know conditions at '{}'.".format(trigger.group(2)))
            return
        bot.say(format_output(trigger.group(2), tags[trigger.group(2)]))
    else:
        for name, data in tags.items():
            bot.say(format_output(name, data))
