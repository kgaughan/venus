from ConfigParser import ConfigParser
import sys
import urllib
import urlparse

import rdflib
from rdflib.namespace import DC, FOAF, RDF, RDFS

from planet.config import downloadReadingList


inheritable_options = ['online_accounts']


def load_accounts(config, section):
    accounts = {}
    if config.has_option(section, 'online_accounts'):
        values = config.get(section, 'online_accounts')
        for account_map in values.split('\n'):
            try:
                homepage, mapping = account_map.split('|')
                accounts[homepage] = mapping
            except:
                pass

    return accounts


def load_graph(rdf, base_uri):
    if isinstance(rdf, rdflib.Graph):
        return rdf

    if hasattr(rdf, 'read'):
        rdf = rdf.read()

    graph = rdflib.Graph()
    graph.parse(data=rdf, publicID=base_uri)
    return graph


# input = foaf, output = ConfigParser
def foaf2config(rdf, config, subject=None, section=None):

    if not config or not config.sections():
        return

    # there should be only be 1 section
    if not section:
        section = config.sections().pop()

    # account mappings, none by default
    # form: accounts = {url to service homepage (as found in FOAF)}|{URI template}\n*
    # example: http://del.icio.us/|http://del.icio.us/rss/{foaf:accountName}
    accounts = load_accounts(config, section)

    depth = 0

    if config.has_option(section, 'depth'):
        depth = config.getint(section, 'depth')

    model = load_graph(rdf, section)

    rss = rdflib.Namespace('http://purl.org/rss/1.0/')

    for person, _, value in model.triples((subject, FOAF.weblog, None)):
        title = model.value(subject=person, predicate=FOAF.name)
        # title is required (at the moment)
        if not title:
            title = model.value(subject=person, predicate=DC.title)
        if not title:
            continue

        # blog is optional
        feed = model.value(subject=value, predicate=RDFS.seeAlso)
        if feed and rss.channel == model.value(subject=feed,
                                               predicate=RDF.type):
            feed = str(feed)
            if not config.has_section(feed):
                config.add_section(feed)
                config.set(feed, 'name', str(title))

        # now look for OnlineAccounts for the same person
        if len(accounts):
            for acc in model.objects(person, FOAF.holdsAccount):
                acc_home = model.value(subject=acc,
                                       predicate=FOAF.accountServiceHomepage)
                acc_name = model.value(subject=acc,
                                       predicate=FOAF.accountName)

                if not acc_home or not acc_name:
                    continue
                acc_home = str(acc_home)
                if acc_home not in accounts:
                    continue

                # shorten feed title a bit
                try:
                    service_title = urlparse.urlsplit(acc_home)[1]
                except:
                    service_title = str(acc_home)

                feed = accounts[acc_home].replace("{foaf:accountName}",
                                                  acc_name)
                if not config.has_section(feed):
                    config.add_section(feed)
                    config.set(feed, 'name', "%s (%s)" % (title,
                                                          service_title))

        if depth > 0:
            # now the fun part, let's go after more friends
            for friend in model.objects(person, FOAF.knows):
                see_also = model.values(subject=friend, predicate=RDFS.seeAlso)
                if not see_also:
                    continue

                see_also = str(see_also)
                if not config.has_section(see_also):
                    config.add_section(see_also)
                    copy_options(config, section, see_also,
                                 {'content_type': 'foaf',
                                  'depth': str(depth - 1)})
                try:
                    downloadReadingList(see_also, config,
                        lambda data, subconfig: friend2config(model, friend, see_also, subconfig, data),
                        False)
                except:
                    pass


def copy_options(config, parent_section, child_section, overrides=None):
    if overrides is None:
        overrides = {}

    for option in config.options(parent_section):
        if option not in inheritable_options:
            continue
        if option not in overrides:
            config.set(child_section, option, config.get(parent_section, option))

    for option, value in overrides.items():
        config.set(child_section, option, value)


def friend2config(friend_model, friend, seeAlso, subconfig, data):
    model = load_graph(data, seeAlso)

    for same_friend in model.subjects(RDF.type, FOAF.Person):
        # maybe they have the same uri
        if friend == same_friend:
            foaf2config(model, subconfig, same_friend)
            return

        # FOAF InverseFunctionalProperties
        for ifp in [FOAF.mbox, FOAF.mbox_sha1sum,
                    FOAF.jabberID, FOAF.aimChatID, FOAF.icqChatID,
                    FOAF.yahooChatID, FOAF.msnChatID,
                    FOAF.homepage, FOAF.weblog]:
            prop = model.value(subject=same_friend, predicate=ifp)
            if prop and prop == friend_model.value(subject=friend,
                                                   predicate=ifp):
                foaf2config(model, subconfig, same_friend)
                return


if __name__ == "__main__":
    config = ConfigParser()

    for uri in sys.argv[1:]:
        config.add_section(uri)
        foaf2config(urllib.urlopen(uri), config, section=uri)
        config.remove_section(uri)

    config.write(sys.stdout)
