import wx

from spb_bet.ui.main_window import MainWindow


def main():
    app = wx.App(False)

    window = MainWindow()
    window.Show()

    app.MainLoop()


if __name__ == "__main__":
    main()