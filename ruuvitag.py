from sopel import module, formatting, tools
from sopel.config.types import StaticSection, ValidatedAttribute
import json
import requests
import google.auth.transport.requests
from google.oauth2.service_account import IDTokenCredentials
import re


LOGGER = tools.get_logger('ruuvitag')


class RuuvitagError(Exception):
    pass


class RuuvitagSection(StaticSection):
    sa_json = ValidatedAttribute('sa_json', str)
    latest_endpoint = ValidatedAttribute('latest_endpoint', str)
    trend_endpoint = ValidatedAttribute('trend_endpoint', str)
    trend_interval = ValidatedAttribute('trend_interval', int)


def setup(bot):
    bot.config.define_section('ruuvitag', RuuvitagSection)


def configure(config):
    config.define_section('ruuvitag', RuuvitagSection, validate=False)
    config.ruuvitag.configure_setting(
            'sa_json',
            ('Where is the GCP service account key file '
                'located at (aka filename)?'))
    config.ruuvitag.configure_setting(
            'latest_endpoint',
            ('What is the GCP cloud function endpoint '
                'URL to call for latest data?'))
    config.ruuvitag.configure_setting(
            'trend_endpoint',
            ('What is the GCP cloud function endpoint '
                'URL to call for trend data?'))
    config.ruuvitag.configure_setting(
            'trend_interval',
            ('What is the trend lookup interval in '
                '(positive) minutes?'))


def invoke_endpoint(url, id_token):
    LOGGER.debug("Querying: {}".format(url))
    headers = {'Authorization': 'Bearer ' + id_token}

    r = requests.get(url, headers=headers)

    if r.status_code not in [200, 204]:
        raise RuuvitagError(
                ("Calling API endpoint failed with "
                    "HTTP status code: {}").format(r.status_code))

    return r.content.decode('utf-8')


def format_trend_output(slope):
    if slope == 0:
        return formatting.color("-", formatting.colors.GREEN)
    elif slope > 0:
        return formatting.color("^", formatting.colors.RED)
    elif slope < 0:
        return formatting.color("v", formatting.colors.BLUE)


def format_tag_output(name, data):
    if data["latest"] is None:
        return "No condition data for '{}' available.".format(name)

    return ("Conditions at '{}' are: {} {}C, {} {}hPa, "
            "{} {}% rel. humidity").format(
        name,
        format_trend_output(data["trend"]["temperature"]),
        round(data["latest"]["temperature"], 1),
        format_trend_output(data["trend"]["atmospheric_pressure"]),
        round(data["latest"]["atmospheric_pressure"], 1),
        format_trend_output(data["trend"]["humidity"]),
        round(data["latest"]["humidity"], 1)
        )


def credentials_for_service(config, url):
    credentials = IDTokenCredentials.from_service_account_file(
        config.ruuvitag.sa_json,
        target_audience=url)

    request = google.auth.transport.requests.Request()
    credentials.refresh(request)

    return credentials


def fetch_tags(config):
    latest_credentials = credentials_for_service(
            config,
            config.ruuvitag.latest_endpoint)
    trend_credentials = credentials_for_service(
            config,
            config.ruuvitag.trend_endpoint)

    response = invoke_endpoint(
            config.ruuvitag.latest_endpoint,
            latest_credentials.token)

    tags = dict()
    for tag in json.loads(response):
        tags[tag["name"]] = dict()
        # store latest data
        tags[tag["name"]]["latest"] = tag["data"]
        # fetch the trend data for each of the variables we are interested in
        fields = ['temperature', 'atmospheric_pressure', 'humidity']
        tags[tag["name"]]["trend"] = dict()
        for field in fields:
            endpoint_with_args = "{}?tag={}&field={}&interval={}".format(
                    config.ruuvitag.trend_endpoint,
                    tag["name"],
                    field,
                    config.ruuvitag.trend_interval)
            trend_json = json.loads(invoke_endpoint(
                endpoint_with_args,
                trend_credentials.token))
            # store trend data
            tags[tag["name"]]["trend"][field] = trend_json["slope"]

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
    (if available) for a requested Ruuvi tag with trend indicators"""

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
