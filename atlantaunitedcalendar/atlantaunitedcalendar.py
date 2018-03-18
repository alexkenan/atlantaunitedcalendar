#!/usr/bin/env python3
"""
Parse https://www.atlutd.com/schedule to get a list of match events and update a Google calendar with
match info

"""
#####################################
#    LAST UPDATED     17 MAR 2017   #
#####################################
import httplib2
import os
import datetime
import argparse
from string import capwords
from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
import requests
from bs4 import BeautifulSoup
flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
SCOPES = 'https://www.googleapis.com/auth/calendar'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'Atlanta United Match Calendar'


def get_html(website: str) -> str:
    """
    Return HTML of a website, in this case https://www.atlutd.com/schedule
    :param website: website URL (str)
    :return: HTML dump (str)
    """
    headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)\
             AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95'}
    return requests.get(website, headers=headers).text


def make_soup(html: str) -> BeautifulSoup:
    """
    Make BeautifulSoup with the HTML dump
    :param html: requests.get.html of a website url (str)
    :return: BeautifulSoup instance
    """
    return BeautifulSoup(html, 'html5lib')


def get_match_info(url: str) -> list:
    """
    Generate a master tuple of match info from the BeautifulSoup instance
    :param url: URL of website to scrape (probably 'https://www.atlutd.com/schedule') (str)
    :return: list of match info []
    """
    response = get_html(url)
    soup = make_soup(response)
    master_list = []
    placeholder = soup.find('ul', class_='schedule_list list-reset').find_all('article')
    for match in placeholder:
        opponent = match.find('div', class_='match_matchup').text.strip()
        opponent = fix_opponent(opponent)

        venue = match.find('div', class_='match_info match_location_short').text.strip()
        date_and_time = match.find('div', class_='match_date').text.strip()
        if 'TBD' in date_and_time:
            date_and_time = date_and_time.replace('TBD', '1:00PM ET')
        date_and_time = fix_datetime(date_and_time)

        try:
            tv_info = match.find('span', class_='match_category').next_sibling.strip()
        except AttributeError:
            tv_info = "No TV info available"

        competition = match.find('span', class_='match_competition ').text.strip()
        if datetime.datetime.now() < date_and_time:
            master_list.append([opponent, venue, date_and_time, tv_info, competition])

    return master_list


def fix_opponent(opponent: str) -> str:
    """
    Fix opponent string that is returned by website scraping
    :param opponent: ATL opponent (str)
    :return: opponent with fixed capitlization (str)
    """
    capitalized = capwords(opponent)
    capitalized = capitalized.replace('At ', '')
    if 'Sc' in capitalized:
        capitalized = capitalized.replace('Sc', 'SC')
    elif 'Fc' in capitalized:
        capitalized = capitalized.replace('Fc', 'FC')

    if 'D.c.' in capitalized:
        capitalized = capitalized.replace('D.c.', 'D.C.')

    return capitalized


def fix_datetime(time: str) -> datetime.datetime:
    """
    Change  into a datetime object
    :param time: Saturday, February 10, 2018 4:00PM ET as (str)
    :return: same as above but as a datetime.datetime object
    """
    if 'ET' in time:
        return datetime.datetime.strptime(time, '%A, %B %d, %Y %I:%M%p ET')
    elif 'TBD' in time:
        return datetime.datetime.strptime(time, '%A, %B %d, %Y TBD')


def get_credentials():
    """
    Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'calendar-python-quickstart.json')

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        print('Storing credentials to ' + credential_path)
    return credentials


def login() -> discovery.build:
    """
    Login to Google and return an authenticated session
    :return: discovery `session`
    """
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)
    return service


def create_event(google: discovery.build, match_bundle: list) -> None:
    """
    Create a Google Calendar event
    :param google: authenticated Google session
    :param match_bundle: list of opponent, venue, time, competition
    :return: None
    """
    opponent = match_bundle[0]
    venue = match_bundle[1]
    time = match_bundle[2]
    watch = match_bundle[3]
    competition = match_bundle[4]

    if venue == 'MERCEDES-BENZ STADIUM':
        filler = 'vs'
    else:
        filler = 'at'

    event = {
        'summary': 'Atlanta United {} {} ({})'.format(filler, opponent, competition),
        'location': '{}'.format(venue),
        'description': 'TV: {}\nAtlanta United {} {} ({})'.format(watch, filler, opponent, competition),
        'start': {
            # 'dateTime': '{0:%Y-%m-%dT%H:%M:00-04:00}'.format(time),
            'dateTime': '{0:%Y-%m-%dT%H:%M:00}'.format(time),
            'timeZone': 'America/New_York',
        },
        'end': {
            # 'dateTime': '{0:%Y-%m-%dT%H:%M:00-04:00}'.format(time + datetime.timedelta(hours=2)),
            'dateTime': '{0:%Y-%m-%dT%H:%M:00}'.format(time + datetime.timedelta(hours=2)),
            'timeZone': 'America/New_York',
        },
        'recurrence': [],
        'attendees': [],
        'reminders': {},
    }
    calendar_id = '3cdkhu8tso8o1i3vlv3fqa4oqk@group.calendar.google.com'
    google.events().insert(calendarId=calendar_id, body=event).execute()


def update_events(google: discovery.build, event_list: list, match_bundle: list) -> None:
    """
    Compare Google Events to match_bundle matches and update events
    :param google: authenticated Google session (discovery.build)
    :param event_list: master list of event ids (list)
    :param match_bundle: list of opponent, venue, time, competition (list)
    :return: None
    """
    calendar_id = '3cdkhu8tso8o1i3vlv3fqa4oqk@group.calendar.google.com'
    # if len(event_list) != len(match_bundle):
    if False:
        # At least one match needs to be added
        pass
    else:
        for index, event in enumerate(event_list):
            opponent = match_bundle[index][0]
            venue = match_bundle[index][1]
            time = match_bundle[index][2]
            watch = match_bundle[index][3]
            competition = match_bundle[index][4]

            if venue == 'MERCEDES-BENZ STADIUM':
                filler = 'vs'
            else:
                filler = 'at'

            old_event = google.events().get(calendarId=calendar_id, eventId=event).execute()
            old_event_summary = old_event['summary']
            old_event_location = old_event['location']
            old_event_description = old_event['description']
            old_event_start_time = old_event['start'].get('dateTime', old_event['start'].get('date'))

            bundle_event_summary = 'Atlanta United {} {} ({})'.format(filler, opponent, competition)
            bundle_event_location = '{}'.format(venue)
            bundle_event_description = 'TV: {}\nAtlanta United {} {} ({})'.format(watch, filler, opponent, competition)
            bundle_event_start_time = '{0:%Y-%m-%dT%H:%M:00-05:00}'.format(time)

            if old_event_start_time != bundle_event_start_time:
                update_individual_event(google, event, 'start.dateTime', bundle_event_start_time)

            if old_event_summary != bundle_event_summary:
                update_individual_event(google, event, 'summary', bundle_event_summary)

            if old_event_location != bundle_event_location:
                update_individual_event(google, event, 'location', bundle_event_location)

            if old_event_description != bundle_event_description:
                update_individual_event(google, event, 'description', bundle_event_description)


def update_individual_event(google: discovery.build, event_id: str, parameter: str, new_text: str) -> None:
    """
    Update individual event by event id
    :param google: authenticated Google session
    :param event_id: Event's id
    :param parameter: Parameter to update
    :param new_text: Text to update the new parameter with
    :return: None
    """
    event = google.events().get(calendarId='3cdkhu8tso8o1i3vlv3fqa4oqk@group.calendar.google.com',
                                eventId=event_id).execute()

    event[parameter] = new_text

    if debug:
        print('Updated {}'.format(event['summary']))

    google.events().update(calendarId='3cdkhu8tso8o1i3vlv3fqa4oqk@group.calendar.google.com',
                           eventId=event['id'], body=event).execute()


def write_all_matches(google: discovery.build, match_list: list) -> None:
    """
    Write all matches in match_list to calendar
    :param google: Authenticated google session
    :param match_list: bundle of match info
    :return: None
    """
    for match in match_list:
        create_event(google, match)


def main() -> None:
    """
    Log in via Google Services, scrape match info from https://www.atlutd.com/schedule, update match info
    """
    service = login()
    matches = get_match_info('https://www.atlutd.com/schedule')
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
    events_result = service.events().list(
        calendarId='3cdkhu8tso8o1i3vlv3fqa4oqk@group.calendar.google.com', timeMin=now, maxResults=1000,
        singleEvents=True,
        orderBy='startTime').execute()

    events = events_result.get('items', [])
    event_bundle = []

    for event in events:
        event_bundle.append(event['id'])

    for event in event_bundle:
        service.events().delete(calendarId='3cdkhu8tso8o1i3vlv3fqa4oqk@group.calendar.google.com',
                                eventId=event).execute()

    write_all_matches(service, matches)


if __name__ == '__main__':
    debug = True
    main()
