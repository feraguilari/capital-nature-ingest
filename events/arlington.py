from datetime import datetime
import logging
import os

from bs4 import BeautifulSoup
import re
import requests

from .utils.log import get_logger

logger = get_logger(os.path.basename(__file__))


def get_arlington_events():
    '''
    Gets events for Arlington County (https://today.arlingtonva.us/)

    Parameters:
        None

    Returns:
        event_items (list): a list of dicts, each of which represents an event.
    '''
    startDate = datetime.now().strftime("%Y-%m-%d")
    from_param = 0
    uri = (
        'https://today-service.arlingtonva.us/api/event/elasticevent?'
        f'&StartDate={startDate}T05:00:00.000Z&EndDate=null&TopicCode='
        'ANIMALS&TopicCode=ENVIRONMENT&ParkingAvailable=false&NearBus=false&'
        f'NearRail=false&NearBikeShare=false&From={from_param}&Size=5'
        '&OrderBy=featured&EndTime=86400000'
    )
    try:
        r = requests.get(uri)
    except Exception as e:
        msg = f"Exception making GET request to {uri}: {e}"
        logger.critical(msg, exc_info=True)
        return
    
    data = r.json()
    count = data['count']
    event_items = []
    while from_param < count:
        if from_param == 0:
            items = data['items']
            for item in items:
                event_items.append(item)
        else:
            uri = (
                'https://today-service.arlingtonva.us/api/event/elasticevent?'
                f'&StartDate={startDate}T05:00:00.000Z&EndDate=null&TopicCode'
                '=ANIMALS&TopicCode=ENVIRONMENT&ParkingAvailable=false&'
                'NearBus=false&NearRail=false&NearBikeShare=false&From'
                f'={from_param}&Size=5&OrderBy=featured&EndTime=86400000'
            )
            r = requests.get(uri)
            data = r.json()
            items = data['items']
            for item in items:
                event_items.append(item)
        from_param += 5

    return event_items


def get_event_website(event_name, start_date, end_date):
    params = {
        "SearchTerm": event_name
    }
    uri = f'https://today-service.arlingtonva.us/api/event/elasticevent'
    r = requests.get(uri, params=params)
    data = r.json()
    items = data['items']
    for item in items:
        item = item['vwEventWithLocation']
        item_start_date = schematize_date(item['eventStartDate'])
        item_end_date = schematize_date(item['eventEndDate'])
        if(start_date == item_start_date and end_date == item_end_date):
            return item['eventUrlText']
    return None


def html_textraction(html):
    '''
    Extracts text from html using bs4

    Parameters:
        html (str): a string containing html

    Returns:
        text (str): the text extracted from the html
    '''
    if not html:
        text = "See event website."
    else:
        soup = BeautifulSoup(html, 'html.parser')
        p_tags = soup.find_all('p')
        if p_tags:
            text = ''
            for p in p_tags:
                p_text = p.get_text()
                if "Activity #" not in p_text:
                    text += p_text + ' '
            text = text.strip()
        else:
            text = soup.get_text().strip()
    text = re.sub('  +', ' ', text)

    return text


def parse_event_name(event_name):
    '''
    Clarifies the invasive plant removal event names and gets text from html.

    Parameters:
        event_name (str): the event name as a string

    Returns:
        event_name (str): the parsed event name
    '''
    if any(x in event_name for x in ('RIP', 'RiP', 'Invasive Plant Removal')):
        if "Invasive Plant Removal" in event_name:
            name = re.sub(
                '  +',
                '',
                "".join(i for i in event_name if ord(i) < 128))\
                .replace("RiP", '')\
                .replace(" - ", '')\
                .replace("RIP", '')
            name = re.sub("  +", " ", name).strip()
        else:
            name = re.sub(
                '  +',
                '',
                "".join(i for i in event_name if ord(i) < 128))
            name = name.replace("RiP", '')\
                .replace("RIP", '')\
                .replace(' - ', '')
            name = f'{name} Invasive Plant Removal'
            name = re.sub("  +", " ", name).strip()
        event_name = html_textraction(name)
    else:
        event_name = html_textraction(event_name)

    return event_name


def schematize_date(event_date):
    '''
    Converts a date string like '2019-01-25T00:00:00' into '2019-01-25'
    '''
    try:
        datetime_obj = datetime.strptime(event_date, "%Y-%m-%dT%H:%M:%S")
        schematized_date = datetime.strftime(datetime_obj, "%Y-%m-%d")
    except ValueError as e:
        msg = f"Exception schematizing this {event_date}: {e}"
        logger.error(msg, exc_info=True)
        return ''
    
    return schematized_date


def schematize_events(event_items):
    '''
    Parses the events API output so that it conforms to our schema

    Parameters:
        event_items (list): a list of dicts, each of which represents an event.
                            Output by get_arlington_events()

    Returns:
        events (list): a list of dicts, each being an event in our schema
    '''
    events = []
    for event_item in event_items:
        event_item = event_item['vwEventWithLocation']
        event_name = parse_event_name(event_item['eventName'])
        if 'Task Force' in event_name or 'Forestry Commission' in event_name:
            continue
        event_description = html_textraction(event_item['eventDsc'])
        start_date = schematize_date(event_item['eventStartDate'])
        end_date = schematize_date(event_item['eventEndDate'])
        start_time = event_item['eventStartTime']
        end_time = event_item['eventEndTime']
        event_website = event_item['eventUrlText']
        if event_item['freeOfChargeInd']:
            event_cost = '0'
        elif event_item['eventCostDsc']:
            event_cost_desc = event_item['eventCostDsc']
            event_cost = ''.join(s for s in event_cost_desc if s.isdigit())
        else:
            event_cost = ''
        venue = html_textraction(event_item['locationName'])
        if venue == 'Earth Products Yard' or 'Library' in venue or not venue:
            continue
        if not event_website:
            event_website = get_event_website(event_name, start_date, end_date)
        venue = venue if venue else "See event website"
        event = {'Event Start Date': start_date,
                 'Event End Date': end_date,
                 'Event Start Time': start_time,
                 'Event End Time': end_time,
                 'Event Website': event_website,
                 'Event Name': event_name,
                 'Event Venue Name': venue,
                 'Event Cost': event_cost,
                 'Event Description': event_description,
                 'Timezone': 'America/New_York',
                 'Event Organizers': "Arlington Parks",
                 'Event Currency Symbol': '$',
                 'All Day Event': False,
                 'Event Category': ''}
        events.append(event)

    return events


def main():
    event_items = get_arlington_events()
    events = schematize_events(event_items)
    return events


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    events = main()
    print(len(events))
