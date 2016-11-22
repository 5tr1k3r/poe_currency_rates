"""This tool collects Path of Exile currency rates from currency.poe.trade."""

import sys

import pyperclip
import requests
from PyQt4 import QtGui, QtCore
from bs4 import BeautifulSoup

LEAGUE = 'Essence'
BASE_URL = 'http://currency.poe.trade/'
AVERAGE_SETTING = 5                         # How many results to use for average value.
REFRESH_SETTING = 30 * 60 * 1000            # Update the table each x min

HOR_HEADERS = ['   Best   ', 'Average', '#', 'Inverse best', 'Inverse avg', '#', '\u0394']
QUERIES_FILENAME = 'queries2.txt'


class QueryData:
    """Contains data related to one query (whether direct or inverse).
    Gets it from individual currency search page.
    """
    def __init__(self, link, blank=0):
        self.best = 0
        self.avg = 0
        self.amount = 0
        self.ign = ''
        self.username = ''
        self.sellvalue = 0
        self.buyvalue = 0
        self.stock = 0

        if blank:
            return

        current_counter = 0

        soup = get_site_contents(link)
        results = soup.find_all(class_='displayoffer')
        self.amount = len(results)

        # First deal = best deal.
        self._get_best_rate(results[0])

        for n, one_result in enumerate(results[1:]):
            current_rate = self._get_current_rate(one_result)

            # If a deal is too big or too small (not legit).
            if current_rate > self.best * 2 or current_rate < self.best / 2:
                self.amount -= 1
            elif current_counter < AVERAGE_SETTING:
                self.avg += current_rate
                current_counter += 1

        if current_counter != 0:
            self.avg = round(self.avg / current_counter, 2)

    @staticmethod
    def _get_current_rate(result):
        min_value, max_value = min_max(float(result['data-buyvalue']),
                                       float(result['data-sellvalue']))
        return round(max_value / min_value, 2)

    def _get_best_rate(self, first_res):
        self.best = self._get_current_rate(first_res)
        self.ign = first_res['data-ign']
        self.username = first_res['data-username']
        self.sellvalue = first_res['data-sellvalue']
        self.buyvalue = first_res['data-buyvalue']
        try:
            self.stock = first_res['data-stock']
        except KeyError:
            self.stock = 0


class Query:
    """Parse a query string like 'buy silver with chaos + inverse'."""
    CURRENCY = ('', 'alteration', 'fusing', 'alchemy', 'chaos', 'gcp', 'exalted', 'chromatic',
                'jeweller', 'chance', 'chisel', 'scouring', 'blessed', 'regret', 'regal',
                'divine', 'vaal', 'wisdom', 'portal', 'scrap', 'whetstone', 'bauble',
                'transmutation', 'augmentation', 'mirror', 'eternal', 'perandus_coin', 'dusk',
                'midnight', 'dawn', 'noon', 'grief', 'rage', 'hope', 'ignorance', 'silver',
                'eber', 'yriel', 'inya', 'volkuur', 'offering')

    def __init__(self, query_string: str) -> None:
        self.data = None
        self.inv_data = None

        self.query_string = query_string
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

        self.parse()

    def parse(self):
        """PARSE"""
        link = self._construct_url(self.want_index, self.have_index)
        self.data = QueryData(link)

        # If there is "+ inverse" keyword in the query, we
        # inverse the currencies and make the search again.
        link = self._construct_url(self.have_index, self.want_index)
        if self.inverse:
            self.inv_data = QueryData(link)
        else:
            self.inv_data = QueryData(link, blank=1)

    @staticmethod
    def _construct_url(x, y):
        return BASE_URL + 'search?league={}&online=x&want={}' \
                          '&have={}'.format(LEAGUE, x, y)

    def construct_trade_msg(self, inverse=0):
        """Construct a poe.trade style trade message and copy it in the clipboard."""

        # Getting rid of decimal part if the number is actually integer.
        # Maybe there is a function/formatting that does it, i haven't found any.
        # NOTE: it would make "Hardcore+Prophecy", with "+" if there are 2 words
        # so need to deal with this later.
        if not inverse:
            buyvalue = self._remove_decimal_part(self.data.buyvalue)
            sellvalue = self._remove_decimal_part(self.data.sellvalue)
            message = '@{} Hi, I\'d like to buy your {} {} for my {} {} in ' \
                      '{}.'.format(self.data.ign, sellvalue, self.want,
                                   buyvalue, self.have, LEAGUE)
        else:
            buyvalue = self._remove_decimal_part(self.inv_data.buyvalue)
            sellvalue = self._remove_decimal_part(self.inv_data.sellvalue)
            message = '@{} Hi, I\'d like to buy your {} {} for my {} {} in ' \
                      '{}.'.format(self.inv_data.ign, sellvalue, self.have,
                                   buyvalue, self.want, LEAGUE)

        pyperclip.copy(message)

    @staticmethod
    def _remove_decimal_part(value: str):
        if value.endswith('.0'):
            value = value[:-2]
        return value


class Window(QtGui.QWidget):
    """Basic Qt window for the tool."""

    def __init__(self):
        super(Window, self).__init__()
        self.progress = None
        self.last_update = None
        self.grid = None
        self.table = None
        self.deals = None
        self.row_position = None
        self.deal = None

        self._init_window()
        self._set_up_grid_and_table()
        self._make_last_update_label()
        self._make_progress_bar()

        self.update_table()

        self.grid.addWidget(self.table, 0, 0)

        self._make_refresh_button()
        self._set_up_timer()
        self._handle_clicking_on_cell()

        self.show()  # Actually showing the window/gui here.

    def _init_window(self):
        self.setGeometry(600, 300, 535, 600)
        self.setWindowTitle('Currency in {}, average of top{}, '
                            'refresh every {} min'.format(LEAGUE, AVERAGE_SETTING,
                                                          REFRESH_SETTING / 60000))
        self.setWindowIcon(QtGui.QIcon('Exalted_Orb.png'))

    def _make_last_update_label(self):
        self.last_update = QtGui.QLabel(self)
        # noinspection PyArgumentList
        self.last_update.setText('Last updated: ' + QtCore.QTime.currentTime().toString())
        self.last_update.move(400, 570)
        self.last_update.resize(self.last_update.sizeHint())

    def _make_progress_bar(self):
        self.progress = QtGui.QProgressBar(self)
        self.progress.setGeometry(170, 545, 110, 10)

    def _set_up_grid_and_table(self):
        # Grid layout
        self.grid = QtGui.QGridLayout()
        self.setLayout(self.grid)

        self.table = QtGui.QTableWidget(self)
        self.table.setColumnCount(len(HOR_HEADERS))

    def _make_refresh_button(self):
        btn = QtGui.QPushButton('Refresh', self)
        btn.resize(btn.sizeHint())
        btn.move(170, 560)
        # noinspection PyUnresolvedReferences
        btn.clicked.connect(self.update_table)

    def _set_up_timer(self):
        timer = QtCore.QTimer(self)
        # noinspection PyUnresolvedReferences
        timer.timeout.connect(self.update_table)
        timer.start(REFRESH_SETTING)        # Update the table each 15 min

    def _handle_clicking_on_cell(self):
        # Put a message into clipboard if you click a best deal cell
        # noinspection PyUnresolvedReferences
        self.table.cellClicked.connect(self.contact_seller)

    def _fill_cells(self):
        deal = self.deal
        needed_fields = (deal.data.best, deal.data.avg, deal.data.amount,
                         deal.inv_data.best, deal.inv_data.avg, deal.inv_data.amount)

        for i, element in enumerate(needed_fields):
            # Ignore empty/zero values.
            if element:
                # Explicitly convert each field to string and add it to subsequent cell
                self.table.setItem(self.row_position, i, QtGui.QTableWidgetItem(str(element)))

    def _make_relative_diff(self):
        # Making relative difference column:
        deal = self.deal

        if deal.inv_data.avg:
            min_value, max_value = min_max(deal.data.avg, deal.inv_data.avg)
            relative_difference = round((max_value / min_value - 1) * 100, 1)
            self.table.setItem(self.row_position, 6,
                               QtGui.QTableWidgetItem(str(relative_difference) + '%'))

    def _adding_tooltips(self, n):
        # Adding tooltips with account name and currency is stock
        deal = self.deal

        if deal.data.best:
            self.table.item(n, 0).setToolTip(
                'account: {}\nign: {}\nstock: {} '
                '{}'.format(deal.data.username,
                            deal.data.ign,
                            deal.data.stock,
                            deal.want))
        if deal.inv_data.best:
            self.table.item(n, 3).setToolTip(
                'account: {}\nign: {}\nstock: {} '
                '{}'.format(deal.inv_data.username,
                            deal.inv_data.ign,
                            deal.inv_data.stock,
                            deal.have))

    def update_table(self):
        """Populate the table with new data."""
        vert_headers = []  # Create a list for vertical headers.

        if self.deals:
            old_deals = self.deals
        else:
            old_deals = None

        with open(QUERIES_FILENAME, 'r') as f:
            self.deals = self.interpret_currency_search(f.read())

        self.table.setRowCount(0)           # Effectively clearing the table if it has anything

        for n, deal in enumerate(self.deals):
            self.deal = deal
            vert_headers.append(deal.header)
            # Get the amount of rows.
            self.row_position = self.table.rowCount()
            # And add a new row in the end.
            self.table.insertRow(self.row_position)

            self._fill_cells()
            self._make_relative_diff()

            self.highlight_deals()
            self.highlight_inverse_deals()

            # Coloring background green if currency goes up or red if it goes down, after refresh.
            if old_deals:
                self.emphasize_trend(old_deals[n].data.avg)
                self.emphasize_inverse_trend(old_deals[n].inv_data.avg)

            self._adding_tooltips(n)

        # We have 4 fixed columns/horizontal headers.
        self.table.setHorizontalHeaderLabels(HOR_HEADERS)
        # We gathered all the vertical headers in the previous step. Now we apply them.
        self.table.setVerticalHeaderLabels(vert_headers)

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

        # noinspection PyArgumentList
        self.last_update.setText('Last updated: ' + QtCore.QTime.currentTime().toString())

    def contact_seller(self, row, col):
        """Make a trade message and copy it in the clipboard."""
        if col == 0 and self.deals[row].data.best:
            self.deals[row].construct_trade_msg()
        if col == 3 and self.deals[row].inv_data.best:
            self.deals[row].construct_trade_msg(inverse=1)

    def emphasize_trend(self, old):
        """Change the background according to rate change:
        - light red if it went down
        - light green if it went up
        """
        deal = self.deal

        if deal.data.avg < old:
            self.table.item(self.row_position, 1).setBackground(QtGui.QColor(255, 230, 230))
        if deal.data.avg > old:
            self.table.item(self.row_position, 1).setBackground(QtGui.QColor(230, 255, 230))

    def emphasize_inverse_trend(self, old):
        """Change the background according to rate change:
        - light red if it went down
        - light green if it went up
        """
        deal = self.deal

        if deal.inv_data.avg < old:
            self.table.item(self.row_position, 4).setBackground(QtGui.QColor(255, 230, 230))
        if deal.inv_data.avg > old:
            self.table.item(self.row_position, 4).setBackground(QtGui.QColor(230, 255, 230))

    def highlight_deals(self):
        """Make the deal background green if it's pretty good."""
        deal = self.deal
        if deal.data.best:
            min_value, max_value = min_max(deal.data.best, deal.data.avg)
            if min_value / max_value < 0.96:
                self.table.item(self.row_position, 0).setBackground(QtGui.QColor(161, 212, 144))

        # Make the deal background bright green if it's awesome.
        if deal.data.best:
            min_value, max_value = min_max(deal.data.best, deal.data.avg)
            if min_value / max_value < 0.92:
                self.table.item(self.row_position, 0).setBackground(QtGui.QColor(67, 245, 7))

    def highlight_inverse_deals(self):
        """Make the deal background green if it's pretty good."""
        deal = self.deal
        if deal.inv_data.best:
            min_value, max_value = min_max(deal.inv_data.best, deal.inv_data.avg)
            if min_value / max_value < 0.96:
                self.table.item(self.row_position, 3).setBackground(QtGui.QColor(161, 212, 144))

        # Make the deal background bright green if it's awesome.
        if deal.inv_data.best:
            min_value, max_value = min_max(deal.inv_data.best, deal.inv_data.avg)
            if min_value / max_value < 0.92:
                self.table.item(self.row_position, 3).setBackground(QtGui.QColor(67, 245, 7))

    def interpret_currency_search(self, queries):
        """Parse our queries which are written like such: 'buy chromatic with chaos'."""
        all_deals = []

        completed = 0
        self.progress.setValue(completed)

        # Cycle through all lines of the query(-ies).
        for i, query_string in enumerate(queries.splitlines()):
            query = Query(query_string)

            all_deals.append(query)

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


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    GUI = Window()
    sys.exit(app.exec_())
