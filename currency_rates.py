"""This tool collects Path of Exile currency rates from currency.poe.trade."""

import sys
from collections import namedtuple

import pyperclip
import requests
from PyQt4 import QtGui, QtCore
from bs4 import BeautifulSoup

LEAGUE = 'Essence'
AVERAGE_SETTING = 5                         # How many results to use for average value.
REFRESH_SETTING = 30 * 60 * 1000            # Update the table each x min
Deal = namedtuple('Deal', ['query', 'best', 'avg', 'amount', 'inverse_best', 'inverse_avg',
                           'inverse_amount', 'best_contact_data', 'inverse_best_contact_data'])

HOR_HEADERS = ['   Best   ', 'Average', '#', 'Inverse best', 'Inverse avg', '#', '\u0394']
QUERIES_FILENAME = 'queries2.txt'


class Query:
    """Parse a query string like 'buy silver with chaos + inverse'."""
    CURRENCY = ('', 'alteration', 'fusing', 'alchemy', 'chaos', 'gcp', 'exalted', 'chromatic',
                'jeweller', 'chance', 'chisel', 'scouring', 'blessed', 'regret', 'regal',
                'divine', 'vaal', 'wisdom', 'portal', 'scrap', 'whetstone', 'bauble',
                'transmutation', 'augmentation', 'mirror', 'eternal', 'perandus_coin', 'dusk',
                'midnight', 'dawn', 'noon', 'grief', 'rage', 'hope', 'ignorance', 'silver',
                'eber', 'yriel', 'inya', 'volkuur', 'offering')

    def __init__(self, query_string: str) -> None:
        split_query = query_string.split()  # type: list

        # If there are 6 words in the query, there must be an inverse request
        self.inverse = len(split_query) == 6  # type: bool

        self.want = split_query[1]
        self.have = split_query[3]

        # Get the index for each currency, i.e. 6 for exalted, 9 for chance etc.
        self.want_index = self.CURRENCY.index(self.want)  # type: int
        self.have_index = self.CURRENCY.index(self.have)  # type: int

        # Take only first 4 words so "+ inverse" isn't printed out.
        self.header = ' '.join(split_query[0:4])


class Window(QtGui.QWidget):
    """Basic Qt window for the tool."""
    BASE_URL = 'http://currency.poe.trade/'

    def __init__(self):
        super(Window, self).__init__()
        self.progress = None
        self.last_update = None
        self.table = None
        self.deals = None

        self.setGeometry(600, 300, 535, 600)
        self.setWindowTitle('Currency in {}, average of top{}, '
                            'refresh every {} min'.format(LEAGUE, AVERAGE_SETTING,
                                                          REFRESH_SETTING / 60000))
        self.setWindowIcon(QtGui.QIcon('Exalted_Orb.png'))

        self.home()

    def home(self):
        """Prepare to show the window and handle signals."""
        # Grid layout
        grid = QtGui.QGridLayout()
        self.setLayout(grid)

        self.table = QtGui.QTableWidget(self)
        self.table.setColumnCount(len(HOR_HEADERS))

        self.last_update = QtGui.QLabel(self)
        # noinspection PyArgumentList
        self.last_update.setText('Last updated: ' + QtCore.QTime.currentTime().toString())
        self.last_update.move(400, 570)
        self.last_update.resize(self.last_update.sizeHint())

        self.progress = QtGui.QProgressBar(self)
        self.progress.setGeometry(170, 545, 110, 10)

        self.update_table()

        grid.addWidget(self.table, 0, 0)

        btn = QtGui.QPushButton('Refresh', self)
        btn.resize(btn.sizeHint())
        btn.move(170, 560)
        # noinspection PyUnresolvedReferences
        btn.clicked.connect(self.update_table)

        timer = QtCore.QTimer(self)
        # noinspection PyUnresolvedReferences
        timer.timeout.connect(self.update_table)
        timer.start(REFRESH_SETTING)        # Update the table each 15 min

        # Put a message into clipboard if you click a best deal cell
        # noinspection PyUnresolvedReferences
        self.table.cellClicked.connect(self.contact_seller)

        self.show()  # Actually showing the window/gui here.

    def update_table(self):
        """Populate the table with new data."""
        vert_headers = []  # Create a list for vertical headers.

        if self.deals:
            old_deals = self.deals
        else:
            old_deals = None

        with open(QUERIES_FILENAME, 'r') as f:
            self.deals = self.interpret_currency_search(f.read())  # TODO: make it a class

        self.table.setRowCount(0)           # Effectively clearing the table if it has anything

        for n, deal in enumerate(self.deals):

            vert_headers.append(deal.query.header)
            # Get the amount of rows.
            row_position = self.table.rowCount()
            # And add a new row in the end.
            self.table.insertRow(row_position)
            # Cycle through all the fields except 'query' and fields with contact data
            for i, element in enumerate(deal[1:7]):
                # Ignore empty/zero values.
                if element:
                    # Explicitly convert each field to string and add it to subsequent cell
                    self.table.setItem(row_position, i, QtGui.QTableWidgetItem(str(element)))

            # Making relative difference column:
            if deal.inverse_avg:
                min_value, max_value = min_max(deal.avg, deal.inverse_avg)
                relative_difference = round((max_value / min_value - 1) * 100, 1)
                self.table.setItem(row_position, 6,
                                   QtGui.QTableWidgetItem(str(relative_difference) + '%'))

            # Coloring background green if best deal is good:

            self.highlight_decent_deals(deal.best, deal.avg, row_position, 0)
            self.highlight_great_deals(deal.best, deal.avg, row_position, 0)

            self.highlight_decent_deals(deal.inverse_best, deal.inverse_avg, row_position, 3)
            self.highlight_great_deals(deal.inverse_best, deal.inverse_avg, row_position, 3)

            # Coloring background green if currency goes up or red if it goes down, after refresh.
            if old_deals:
                self.emphasize_the_trend(deal.avg, old_deals[n].avg,
                                         row_position, 1)
                self.emphasize_the_trend(deal.inverse_avg, old_deals[n].inverse_avg,
                                         row_position, 4)

            # Adding tooltips with account name and currency is stock
            if deal.best:
                self.table.item(n, 0).setToolTip(
                    'account: {}\nign: {}\nstock: {} '
                    '{}'.format(deal.best_contact_data['username'],
                                deal.best_contact_data['ign'],
                                deal.best_contact_data['stock'],
                                deal.query.want))
            if deal.inverse_best:
                self.table.item(n, 3).setToolTip(
                    'account: {}\nign: {}\nstock: {} '
                    '{}'.format(deal.inverse_best_contact_data['username'],
                                deal.inverse_best_contact_data['ign'],
                                deal.inverse_best_contact_data['stock'],
                                deal.query.have))

        # We have 4 fixed columns/horizontal headers.
        self.table.setHorizontalHeaderLabels(HOR_HEADERS)
        # We gathered all the vertical headers in the previous step. Now we apply them.
        self.table.setVerticalHeaderLabels(vert_headers)

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

        # noinspection PyArgumentList
        self.last_update.setText('Last updated: ' + QtCore.QTime.currentTime().toString())

    def contact_seller(self, row, col):   # TODO: improve this shit so there is no duplicate code
        """Make a trade message and copy it in the clipboard."""
        if col == 0 and self.deals[row].best:
            aaa = self.construct_trade_msg(self.deals[row].best_contact_data['ign'],
                                           self.deals[row].best_contact_data['sellvalue'],
                                           self.deals[row].query.want,
                                           self.deals[row].best_contact_data['buyvalue'],
                                           self.deals[row].query.have)
            pyperclip.copy(aaa)
        if col == 3 and self.deals[row].inverse_best:
            aaa = self.construct_trade_msg(self.deals[row].inverse_best_contact_data['ign'],
                                           self.deals[row].inverse_best_contact_data['sellvalue'],
                                           self.deals[row].query.have,
                                           self.deals[row].inverse_best_contact_data['buyvalue'],
                                           self.deals[row].query.want)
            pyperclip.copy(aaa)

    @staticmethod
    def construct_trade_msg(ign, sellvalue, sellcurrency, buyvalue, buycurrency):
        """Construct a poe.trade style trade message."""
        # Getting rid of decimal part if the number is actually integer.
        # Maybe there is a function/formatting that does it, i haven't found any.
        if sellvalue.endswith('.0'):
            sellvalue = sellvalue[:-2]
        if buyvalue.endswith('.0'):
            buyvalue = buyvalue[:-2]
        # NOTE: it would make "Hardcore+Prophecy", with "+" if there are 2 words
        # so need to deal with this later.
        message = '@{} Hi, I\'d like to buy your {} {} for my {} {} in ' \
                  '{}.'.format(ign, sellvalue, sellcurrency, buyvalue, buycurrency, LEAGUE)
        return message

    def emphasize_the_trend(self, current, old, row, column):
        """Change the background according to rate change:
        - light red if it went down
        - light green if it went up
        """
        if current < old:
            self.table.item(row, column).setBackground(QtGui.QColor(255, 230, 230))
        if current > old:
            self.table.item(row, column).setBackground(QtGui.QColor(230, 255, 230))

    def highlight_decent_deals(self, best_one, avg_one, row, column):
        """Make the deal background green if it's pretty good."""
        if best_one:
            min_value, max_value = min_max(best_one, avg_one)
            if min_value / max_value < 0.96:
                self.table.item(row, column).setBackground(QtGui.QColor(161, 212, 144))

    def highlight_great_deals(self, best_one, avg_one, row, column):
        """Make the deal background bright green if it's awesome."""
        if best_one:
            min_value, max_value = min_max(best_one, avg_one)
            if min_value / max_value < 0.92:
                self.table.item(row, column).setBackground(QtGui.QColor(67, 245, 7))

    def interpret_currency_search(self, queries):
        """Parse our queries which are written like such: 'buy chromatic with chaos'."""
        all_deals = []

        completed = 0
        self.progress.setValue(completed)

        # Cycle through all lines of the query(-ies).
        for i, query_string in enumerate(queries.splitlines()):
            query = Query(query_string)
            # Construct the link.
            link = self.BASE_URL + 'search?league={}&online=x&want={}' \
                                   '&have={}'.format(LEAGUE, query.want_index, query.have_index)
            best, avg, amount, best_contact_data = parse_the_page(link)

            inverse_best = 0
            inverse_avg = 0
            inverse_amount = 0

            inverse_best_contact_data = {'ign': 0,  # TODO: make contact data a class
                                         'username': 0,
                                         'sellvalue': 0,
                                         'buyvalue': 0,
                                         'stock': 0}

            # If there is "+ inverse" keyword in the query, we
            # inverse the currencies and make the search again.
            if query.inverse:
                link = self.BASE_URL + 'search?league={}&online=x&want={}' \
                                       '&have={}'.format(LEAGUE, query.have_index,
                                                         query.want_index)
                (inverse_best, inverse_avg, inverse_amount,
                 inverse_best_contact_data) = parse_the_page(link)

            # Fill up our list with namedtuples
            all_deals.append(Deal(query, best, avg, amount, inverse_best, inverse_avg,
                                  inverse_amount, best_contact_data, inverse_best_contact_data))

            completed = 100 / len(queries.splitlines()) * (i + 1)
            self.progress.setValue(completed)

        return all_deals


def get_site_contents(link):
    """Just a wrapper for mundane stuff."""
    res = requests.get(link)
    res.raise_for_status()          # Raise an exception if something bad happens.
    return BeautifulSoup(res.content, 'lxml')


def min_max(a, b):
    """Get min and max values in a one-liner."""
    c = min(a, b)
    d = max(a, b)
    return c, d


def parse_the_page(link):
    """Check each individual currency search page."""
    current_counter = 0
    best_deal = 0
    average_deal = 0
    best_contact_data = {'ign': 0,
                         'username': 0,
                         'sellvalue': 0,
                         'buyvalue': 0,
                         'stock': 0}

    soup = get_site_contents(link)

    results = soup.find_all(class_='displayoffer')

    number_of_deals = len(results)

    for n, one_result in enumerate(results):
        min_value, max_value = min_max(float(one_result['data-buyvalue']),
                                       float(one_result['data-sellvalue']))
        current_deal = round(max_value / min_value, 2)
        # print(current_deal, end=' ')

        # First deal = best deal.
        if n == 0:
            best_deal = current_deal
            best_contact_data['ign'] = one_result['data-ign']
            best_contact_data['username'] = one_result['data-username']
            best_contact_data['sellvalue'] = one_result['data-sellvalue']
            best_contact_data['buyvalue'] = one_result['data-buyvalue']
            try:
                best_contact_data['stock'] = one_result['data-stock']
            except KeyError:
                best_contact_data['stock'] = 0

        # If a deal is too big or too small (not legit).
        if current_deal > best_deal * 2 or current_deal < best_deal / 2:
            number_of_deals -= 1
        elif current_counter < AVERAGE_SETTING:
            average_deal += current_deal
            current_counter += 1

    if current_counter != 0:
        average_deal = round(average_deal / current_counter, 2)

    # print('>>>>>', number_of_deals)

    return best_deal, average_deal, number_of_deals, best_contact_data


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    GUI = Window()
    sys.exit(app.exec_())
