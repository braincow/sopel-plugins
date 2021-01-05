from sopel import module
from sopel.config.types import StaticSection, ValidatedAttribute
import json
import requests
import google.auth.transport.requests
from google.oauth2.service_account import IDTokenCredentials
import re


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


def format_tag_output(name, data):
    if data is None:
        return "No condition data for '{}' available.".format(name)

    return "Conditions at '{}' are: {}C, {}hPa, {}% rel. humidity".format(
        name,
        round(data["temperature"], 1),
        round(data["atmospheric_pressure"], 1),
        round(data["humidity"], 1)
        )


def fetch_tags(config):
    credentials = IDTokenCredentials.from_service_account_file(
        config.ruuvitag.sa_json,
        target_audience=config.ruuvitag.endpoint)

    request = google.auth.transport.requests.Request()
    credentials.refresh(request)

    response = invoke_endpoint(config.ruuvitag.endpoint, credentials.token)

    tags = dict()
    for tag in json.loads(response):
        tags[tag["name"]] = tag["data"]

    if len(tags) == 0:
        raise RuuvitagError("No latest Ruuvi tag information available.")

    return tags


@module.commands('ruuvitags')
@module.rate(user=60, channel=10, server=1)
def ruuvitags(bot, trigger):
    """Lists all known Ruuvi tags"""
    tags = fetch_tags(bot.config)
    names = tags.keys()
    names.sort()
    bot.say("I know tags: '{}'".format("', '".join(names)))


@module.commands('ruuvitag')
@module.rate(user=60, channel=10, server=1)
def ruuvitag(bot, trigger):
    """Displays last recorded Bluetooth beacon value
    (if available) for a requested Ruuvi tag"""

    if trigger.group(2) is not None and trigger.group(2) != "":
        tags = fetch_tags(bot.config)

        exp = re.compile(trigger.group(2))
        matched = list(filter(exp.match, list(tags.keys())))
        if len(matched) == 0:
            bot.say(
                ("I dont know Ruuvi tag '{}'. "
                    "Maybe try .ruuvitags to list known tags.").format(
                        trigger.group(2)))
        else:
            for match in matched:
                bot.say(format_tag_output(match, tags[match]))
    else:
        bot.say(
            ("Which Ruuvi tag are you interested at? "
                "Maybe try .ruuvitags first to list known tags."))

# eof
