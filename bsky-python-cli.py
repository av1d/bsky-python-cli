import argparse
import json
import os
import re
import requests
import sys
import urllib3
import uuid

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from PIL import Image
from typing import List, Dict


VERSION = '0.2'

"""
    bsky-python-cli

    Unofficial command line client for posting to BlueSky.
    Supports mentions, hyperlinks, website card (Open Graph meta for embedding in post), multiple images and alt text.
    For your security this will make a copy of your images with the EXIF data stripped prior to posting.

    This software is neither created nor endorsed by Bluesky. Use at your own risk.

    Changelog:
    [02.10.2024]
    - better error handling for some instances
    - Updated Open Graph to grab a title from title tag if og:title is unavailable.
    - Grabs favicon if no og:image, then trys first <img> if no favicon before setting image to none.
"""


#################
### USER SETTINGS
# Username MUST contain '.bsky.social' at the end (or equivalent). Example: 'example.bsky.social'
# Get your application password here: https://bsky.app/settings/app-passwords
BLUESKY_HANDLE       = "YOURNAME.bsky.social"
BLUESKY_APP_PASSWORD = "YOUR-APP-PASSWORD"

EXIT_ON_FAILED_EXIF  = True
"""
    For security, if we fail to strip the EXIF data from your photos,
    exit immediately. If you don't care, set this to False. False
    has the side effect of omitting the image from the post on strip failure.
"""

USE_WEBSITE_CARDS    = True
"""
    Change to False to disable embedding link meta in post.
    Gets first link only, and only if there are no images.
"""

ALT_TEXT_DELIMITER   = '~'
"""
    If you are using more than 1 image and more than 1 alt text,
    this is the character which will separate each alt text. For example (~):
        "image 1 is the sun~image 2 is the sky~image 3 is the moon"
    Make sure you enclose the entire string in quotes as above.
    You likely don't want to use common punctuation here like (!@#$%&*"',.?) and so on.
    This can also be multiple characters, like "ALTTEXTDELIMITER" even, if you like.
"""

LANGUAGE = ["en-US"]
"""
    you can use multiple ISO language codes like ["en-US", "en-AU"].
    see: https://www.andiamo.co.uk/resources/iso-language-codes/
"""

DEBUG = True
"""
    if set to True, dumps the final JSON request for the post for examination.
"""
###
#################


def find_url_data(post_string):  # find URL locations within text
    pattern = re.compile(r'https?://\S+')
    matches = re.findall(pattern, post_string)
    result  = {}
    for i, url in enumerate(matches, start=1):
        start          = post_string.index(url)
        end            = start + len(url)
        result[str(i)] = {"URL": url, "byteStart": start, "byteEnd": end}
    return result


def parse_url_facets(url_data):  # convert URLs in text into 'facets'
    facet_list = []
    for key, value in url_data.items():
        URL       = value['URL']
        byteStart = value['byteStart']
        byteEnd   = value['byteEnd']
        url_facet = {
            "index": {
                "byteStart": int(byteStart),
                "byteEnd": int(byteEnd)
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": str(URL)
                }
            ]
        }
        facet_list.append(url_facet)
    return facet_list


def find_mentions(post_string):  # find handle mentions in text ('@person')
    pattern = re.compile(r'@\w+')
    matches = re.findall(pattern, post_string)
    result  = {}
    for i, handle in enumerate(matches, start=1):
        start = post_string.index(handle)
        end   = start + len(handle)
        result[str(i)] = {"handle": handle, "byteStart": start, "byteEnd": end}
    return result


def get_mention_data(mention):  # get the handle's DID to create the mention facet
    mention_list = []
    for key, value in mention.items():
        if 'handle' in value:
            handle    = value['handle'][1:] + '.bsky.social'
            byteStart = value['byteStart']
            byteEnd   = value['byteEnd']

            resp = requests.get(
                "https://bsky.social/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": handle},
            )
            if resp.status_code == 400:
                return {}  # if handle DID not found, return empty dict

            did = resp.json()["did"]

            mention_facet = {
                  "index": {
                    "byteStart": int(byteStart),
                    "byteEnd": int(byteEnd)
                  },
                  "features": [
                    {
                      "$type": "app.bsky.richtext.facet#mention",
                      "did": str(did)
                    }
                  ]
            }
            mention_list.append(mention_facet)
    return mention_list


def get_token():  # API token
    """
        Get a session token. The API documentation doesn't mention
        expiry so we're just going to grab a new one each time
        until we learn otherwise. ¯\_(ツ)_/¯
    """

    global token

    try:
        resp = requests.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_APP_PASSWORD},
        )

        resp.raise_for_status()
        token = resp.json()

        if 'accessJwt' in token:
            token = resp.json()
            return token
        else:
            print("Error: 'accessJwt' key not found in token")
            print(f"Error: {resp.content}")
            sys.exit(1)

    except requests.exceptions.HTTPError as e:
        print(f"Fatal error: HTTP error occurred: {e}")
        print(f"Response content: {resp.content}")
        sys.exit(1)


def upload_image(image_path):  # upload image, get the blob
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        if len(img_bytes) > 1000000:
            raise Exception(
                f"image file size too large. 1000000 bytes maximum, got: {len(img_bytes)}"
            )
    except:
        return {}

    file_name, file_extension = os.path.splitext(image_path)
    file_extension = file_extension[1:]
    image_mimetype = f"image/{file_extension}"

    resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
        headers={
            "Content-Type": image_mimetype,
            "Authorization": "Bearer " + token["accessJwt"],
        },
        data=img_bytes,
    )

    resp.raise_for_status()
    blob = resp.json()["blob"]
    return blob


def strip_exif_data(image_path):  # delete photo meta
    """
        Client must strip EXIF manually.
        See: https://atproto.com/specs/xrpc#security-and-privacy-considerations
    """
    try:
        output_path = os.path.splitext(image_path)[0] + '.stripped' + os.path.splitext(image_path)[1]
        image = Image.open(image_path)
        image.save(output_path, exif=b'')
        image.close()
        return output_path
    except Exception as e:
        print(f"Failed to strip EXIF data. {e}")
        if EXIT_ON_FAILED_EXIF:  # for security
            print("Exiting. Set EXIT_ON_FAILED_EXIF to False to ignore.")
            sys.exit(1)
        else:  # if user doesn't care, just skip the image
            return {}


def get_website_card(URL):  # aka Open Graph / social card / etc.

    global embed
    embed = {}

    page = requests.get(URL, verify=False)

    if page.status_code == 200:
        try:
            soup = BeautifulSoup(page.content, 'html.parser')

            print("\nFetching Open Graph data:\n")

            try:  # try to find a title
                og_title = soup.find('meta', property='og:title')['content']
            except Exception as e:
                print(f"Error getting og:title or tag doesn't exist: {e}")
                print("Trying to get site title instead")
                for title in soup.find_all('title'):
                    title_search = title.get_text()
                    if title_search:
                        print(f"Found title via <title> tag: {title_search}")
                        og_title = title_search
                    else:
                        print(f"Can't find any title. Setting og:title to the URL {URL}")
                        og_title = str(URL)
            print('--------')

            try:  # see if og:description is defined
                og_description = soup.find('meta', property='og:description')['content']
                if og_description:
                    print(f"Found og:description: {og_description}")
                else:
                    og_description = soup.find('meta', property='Description')['content']
                    if not og_description:
                        print("Setting og:description to empty")
                        og_description = ''
            except Exception as e:
                print(f"Error getting og:description or tag doesn't exist: {e}")
                og_description = ''
            print('--------')

            try:  # try to get some sort of image at all
                og_image = soup.find('meta', property='og:image')['content']
                if og_image:
                    print(f"Found og:image: {og_image}")
            except Exception as e:
                print(f"Error getting og:image or tag doesn't exist. Attempting to use favicon instead: {e}")
                # attempt to grab the favicon if that fails
                favicon_tag = soup.find('link', rel='icon')
                if favicon_tag:
                    favicon_url = favicon_tag['href']
                    og_image = favicon_url
                    print(f"Found image (favicon): {og_image}")
                else:  # try for the first <img> tag
                    print("Can't find favicon. Trying to find the first image on the page.")
                    image = soup.findAll('img', src=True)
                    image = image[0]
                    if image:
                        og_image = image
                        print(f"Found image (first <img> tag): {og_image}")
                    else:   # nothing else we can do
                        print("Finding any images has failed. Nothing else to try. Setting og:image to 'None'")
                        og_image = None
            print('--------')

        except Exception as e:
            raise Exception('Unable to parse Open Graph metadata: {e}')
            sys.exit(1)
    else:
        print(f"Fetching card from URL failed with status code {page.status_code}")
        return {}

    # download the website card image
    if og_image is not None:
        r = requests.get(og_image, allow_redirects=True)
        if r.status_code == 200:
            file_extension = og_image.split('.')[-1]
            file_exists = True
            while file_exists:  # make sure we don't overwrite any local files
                card_filename = str(uuid.uuid4()) + '.' + file_extension
                file_exists = os.path.exists(card_filename)
            open(card_filename, 'wb').write(r.content)
        else:
            print(f"Fetching image {og_image} failed with status code {r.status_code}. Web card will not contain image.")
            return {}

    # upload the image to get the blob
    try:
        blob = upload_image(card_filename)
    except Exception as e:
        erroneous_image_data = str(og_image)
        print(f"Error uploading image (err_1): {erroneous_image_data}: {e}")

    if blob:
        link     = blob['ref']['$link']
        mimeType = blob['mimeType']
        img_size = blob['size']

        embed = {
            "embed": {
                "$type": "app.bsky.embed.external",
                "external": {
                  "uri": str(og_image),
                  "title": str(og_title),
                  "description": str(og_description),
                  "thumb": {
                    "$type": "blob",
                    "ref": {
                      "$link": str(link)
                    },
                    "mimeType": str(mimeType),
                    "size": int(img_size)
                  }
                }
              }
            }

        try:  # delete the image
            os.remove(card_filename)
        except FileNotFoundError:
            print(f"The file '{card_filename}' does not exist.")
        except Exception as e:
            print(f"An error occurred while deleting the file '{card_filename}': {str(e)}")

        return embed
    else:
        erroneous_image_data = str(og_image)
        print(f"Error uploading image (err_2): {erroneous_image_data}")
        return {}


def prepare_post(post_string, image_blob_list = None):

    url_data   = find_url_data(post_string)
    url_facets = parse_url_facets(url_data)
    mentions   = find_mentions(post_string)

    # determine which facets exist, if any
    facet_list = []
    if url_data and mentions:  # if post contains both URL(s) and mention(s)
        mention_facets = get_mention_data(mentions)
        if mention_facets:  # if we found a DID for the handle(s)
            facet_list = url_facets + mention_facets
        else:  # if no DID(s), ignore mentions and just use URL(s)
            facet_list = url_facets
    elif url_data:  # if post contains only URL(s)
        facet_list = url_facets
    elif mentions:  # if post contains only mention(s)
        mention_facets = get_mention_data(mentions)
        if mention_facets:
            facet_list = mention_facets

    now  = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    post = {
        "$type": "app.bsky.feed.post",
        "text": str(post_string),
        "createdAt": now,
        "langs": LANGUAGE,
    }

    """
        If there's a link, get the meta for the first one and embed it.
        Don't add website card if images exist for the post as they can't co-exist.
        The card won't be shown if there are images so it's a waste of resources.
    """
    if USE_WEBSITE_CARDS and url_data and not image_blob_list:
        get_card = get_website_card(url_data['1']['URL'])
        if get_card:
            post.update(get_card)

    # update facets
    if facet_list:
        facets = {
            "facets": facet_list
        }
        post.update(facets)

    # add images if they exist
    if image_blob_list:
        post["embed"] = {}
        images = []
        for image_blob in image_blob_list:
            images.append(image_blob[0])
        post["embed"] = {
            "$type": "app.bsky.embed.images",
            "images": images
        }

    return post


def send_post(prepared_post):

    if DEBUG == True:
        print("+-------------------+")
        print("| DEBUG (post body) |")
        print("+-------------------+\n\n")
        print("```json\n")
        print(prepared_post)
        print("\n```\n+--- end of post body ---+")

    resp = requests.post(
        "https://bsky.social/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {token['accessJwt']}"},
        json={
            "repo": token["did"],
            "collection": "app.bsky.feed.post",
            "record": prepared_post,
        },
    )

    if resp.status_code == 200:
        print("Success! Your message has been posted.")
        #print(json.dumps(resp.json(), indent=2))
    else:
        print(f"Request failed with status code: {resp.status_code}")

    resp.raise_for_status()


def main():

    # command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('text', type=str,
        help='Text of post, enclosed in quotes. Specify \'\' for none.'
            'Post without text must have an image.'
    )
    parser.add_argument('image', type=str, nargs='?',
        help='Image path(s), optional. 4 max. If more than one, separate with commas.'
            'If paths/filesnames have spaces, enclose entire string in quotes.'
            'Example: "/my pix/pic.jpg" or "/my pix/pic.jpg,/my pix/pic2.jpg".'
        )
    parser.add_argument('alt', type=str, nargs='?',
        help='Alt text for image,'
            'optional but recommended to be inclusive of those whom have accessibility disadvantages.'
    )
    args = parser.parse_args()

    # exit if text is empty and there are no images
    if not args.image and args.text == '':
        print("Post text and image fields are empty. Nothing to post.")
        sys.exit(1)

    # get API token
    get_token()

    # if image(s) specified, separate them into a list.
    args_images = args.image
    if args.image:
        if ',' in args_images:
            args_images = args_images.split(',')
            if len(args_images) > 4:
                args_images = args_images[:4]  # trim so only 4 long
        else:
            args_images = [args.image]  # if there's a single image

        # if alt-text(s) specified:
        args_alt_text = args.alt
        if args_alt_text is not None:
            if ALT_TEXT_DELIMITER in args_alt_text:  # if more than 1 alt
                args_alt_text = args_alt_text.split(ALT_TEXT_DELIMITER)  # split at delim
                if len(args_alt_text) > 4:  # if more than 4 specified
                    args_alt_text = args_alt_text[:4]  # trim to 4 elements long
                while len(args_alt_text) < len(args_images):  # pad it out
                    args_alt_text.append('')
            else:
                args_alt_text = [args_alt_text] + [''] * (len(args_images) - 1)  # convert single alt-text to a list with padding
        else:
            args_alt_text = [''] * len(args_images)  # pad it if nothing is specified

        # iterate through each image and corresponding alt text
        blob_list = []
        for img, corresponding_alt_text in zip(args_images, args_alt_text):  # correlation
            stripped_exif = strip_exif_data(img)  # strip exif since Bsky does not
            if stripped_exif:
                image_blob = upload_image(stripped_exif)  # upload pic to API, get blob
                if image_blob:  # if blob was successful, add it
                    alt_text = str(corresponding_alt_text) if corresponding_alt_text else ''
                    temp_array = [{"alt": corresponding_alt_text, "image": image_blob}]
                    blob_list.append(temp_array)
                try:  # delete the temporary stripped file
                    os.remove(stripped_exif)
                except FileNotFoundError:
                    print(f"The file '{stripped_exif}' does not exist.")
                except Exception as e:
                    print(f"An error occurred while deleting the file '{stripped_exif}': {str(e)}")
        if len(args_images) >= 1:
            prepared_post = prepare_post(args.text, blob_list)
    else:  # if post contains no images:
        prepared_post = prepare_post(args.text)

    # finally, post it
    send_post(prepared_post)


if __name__ == "__main__":
    main()
