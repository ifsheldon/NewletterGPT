from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_datetime_from_string
import re
import json
import easyocr
import oss2
import os
from requests_html import HTMLSession

@dataclass
class Tags:
    aigc: bool
    digital_human: bool
    neural_rendering: bool
    computer_graphics: bool
    computer_vision: bool
    robotics: bool
    consumer_electronics: bool

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)


@dataclass
class FeedItem:
    title: str
    link: str
    published: datetime
    with_html_noise: bool
    content: str
    source: str
    summary: Optional[str] = None
    tags: Optional[Tags] = None

    def __eq__(self, other):
        if isinstance(other, FeedItem):
            return self.link == other.link
        else:
            return False

    def __hash__(self):
        return hash(self.link)

    def to_json(self, feed_source: Optional[str] = None) -> str:
        """
        Parse the feed item into a JSON string. Need to use gen_summary_via_llm() first, to ensure that we have a summary.
        :param feed_source: the source of the feed
        :return: JSON string
        """
        assert self.summary is not None, "Get summary first and then parse it into JSON"
        data_dict = {
            "title": self.title,
            "link": self.link,
            "publishTime": self.published.strftime('%Y-%m-%d'),
            "summary": self.summary,
            "tags": None if self.tags is None else self.tags.to_json(),
        }
        if feed_source is not None:
            data_dict["source"] = feed_source
        return json.dumps(data_dict, ensure_ascii=False)


class FeedSource:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self.last_update_time: Optional[datetime] = None

    def get_feeds(self) -> (List[FeedItem], bool, List[FeedItem]):
        """
        Get the feeds from the source. If the source is updated, return the new feeds.
        :return: all feeds, whether the source is updated, new feeds
        """
        feed_items = parse_rss(self.url, self.name)
        latest_update_time = max(feed_items, key=lambda x: x.published).published
        if self.last_update_time is None:
            self.last_update_time = latest_update_time
            return feed_items, True, feed_items
        else:
            if latest_update_time > self.last_update_time:
                new_items = list(filter(lambda x: x.published > self.last_update_time, feed_items))
                self.last_update_time = latest_update_time
                return feed_items, True, new_items
            else:
                return feed_items, False, []


def parse_rss(url: str, source: str) -> List[FeedItem]:
    """
    Parse the RSS feed from the url.
    :param url: URL to RSS feed
    :param source: the name of the source
    :return: feed items
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/113.0"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    root = list(root)[0]
    channel_items = list(root)
    raw_feed_items = list(filter(lambda x: x.tag == "item", channel_items))
    feed_items = []
    for feed_item in raw_feed_items:
        title = feed_item.find("title").text
        link = feed_item.find("link").text
        published = feed_item.find("pubDate").text
        content = feed_item.find("content:encoded",
                                 namespaces={"content": "http://purl.org/rss/1.0/modules/content/"})
        if content is None:
            # if there is no content tag, then we need to parse the html content
            html_content = requests.get(link).text
            soup = BeautifulSoup(html_content, "html.parser")
            content = soup.get_text()
            with_html_noise = True
        else:
            # remove all html tags
            content = re.sub("<.*?>", '', content.text)
            with_html_noise = False

        content = re.sub(r"&\w+;", "", content)

        feed_items.append(FeedItem(title=title,
                                   link=link,
                                   published=parse_datetime_from_string(published),
                                   with_html_noise=with_html_noise,
                                   content=content,
                                   source=source))
    return feed_items


def get_url(url):
    img_url = "None"
    if "qbitai" in url:
        img_url = liangZiWei(url)
    if "jiqizhixin" in url:
        img_url = jiQi(url)
    if "weixin" in url:
        img_url = weiXin(url)
    return img_url


def liangZiWei(web):
    urls=[]
    headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36'
    }

    f = requests.get(web, headers=headers).text
    s = BeautifulSoup(f,'lxml')
    s_imgs = s.find_all('img')
    for s_img in s_imgs:
        if "http" not in s_img['src']:
            img_url = 'http://www.qbitai.com' + s_img['src']
            urls.append(img_url)

    if len(urls)<2:
        url ="None"
    else:
        url = urls[1]
    return url

def jiQi(web):
    urls=[]
    f = requests.get(web).text
    s = BeautifulSoup(f,'lxml')
    s_imgs = s.find_all('img',attrs = {'logo' : False})
    for s_img in s_imgs:
        if "editor" in s_img['src']:
            img_url = s_img['src']
            urls.append(img_url)
    if urls==[]:
        url = "None "
    else:
        url = urls[0]
    return url

def weiXin(web): 
    session = HTMLSession()
    r = session.get(web)
    r.html.render() 
    html_content = r.html.html
    s_imgs = r.html.find('img')

    urls=[]
    for s_img in s_imgs:
        if 'data-src' in s_img.attrs:
            img_url = s_img.attrs['data-src'] 
            urls.append(img_url)
    if len(urls)<1:
        url ="None"
        return url
    
    url = urls[0]
    html = requests.get(url)
    name = web[27:]+'.jpg'
    with open(name, 'wb') as file:
        file.write(html.content)

    reader = easyocr.Reader(['ch_sim','en']) 
    result = reader.readtext(name)
    if len(result)>1:
        if len(result[1])>1:
            if result[0][1] =='此图片来自微信公众平台':
                url = "None"
                return url
    access_key_id = 'bo71Pp26DgpIT9vW'
    access_key_secret = 'r2FaziaNDqBgv4kDQIjgAbcTazv0kB'
    bucket_name = 'gempoll-ai'
    endpoint = 'http://oss-cn-shanghai.aliyuncs.com'
    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)

    object_key = name
    local_file = name
    bucket.put_object_from_file(object_key, local_file)
    url = 'https://gempoll-ai.oss-cn-shanghai.aliyuncs.com/'+name
    os.remove(name)
    return url
