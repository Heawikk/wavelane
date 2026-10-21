import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The administrator's menu: the numbers of the library, every track in it, and the
    place to add more. Only shown to administrators.
*/
Item {
    id: root

    property bool detailOpen: true
    property int tab: 0

    signal showConflicts()

    readonly property var tabs: [
        { value: "0", label: qsTr("Dashboard") },
        { value: "1", label: qsTr("Все треки") },
        { value: "2", label: qsTr("Исполнители") },
        { value: "3", label: qsTr("Загрузка") },
        { value: "4", label: qsTr("Админы") }
    ]

    function openUpload() {
        tab = 3
        upload.openFiles()
    }

    function refresh() {
        if (tab === 0)
            dashboard.refresh()
        else if (tab === 1)
            library.loadCatalogue()
        else if (tab === 2)
            artists.refresh()
        else if (tab === 4)
            team.refresh()
    }

    onTabChanged: refresh()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 52

            Segmented {
                anchors.left: parent.left
                anchors.leftMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                options: root.tabs
                current: String(root.tab)
                onPicked: function(value) { root.tab = parseInt(value) }
            }

            Mono {
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                visible: root.tab === 1
                text: qsTr("Треков: ") + library.catalogue.count + " / " + library.trackCount
                color: Theme.faint
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.border
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            AdminDashboard {
                id: dashboard
                anchors.fill: parent
                visible: root.tab === 0
            }

            // every track, a page at a time as the list is scrolled, with a search; the
            // pencil in the details panel edits the selected one
            ColumnLayout {
                anchors.fill: parent
                visible: root.tab === 1
                spacing: 0

                SearchBox {
                    Layout.fillWidth: true
                    placeholder: qsTr("Найти трек, исполнителя или альбом")
                    onSearched: function(text) { library.searchCatalogue(text) }
                }

                TrackBrowser {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    model: library.catalogue
                    context: "catalogue"
                    detailOpen: root.detailOpen
                    emptyText: qsTr("Ничего не найдено. Загрузить музыку можно на вкладке «Загрузка».")
                    onEndReached: library.loadMoreCatalogue()
                }
            }

            AdminArtists {
                id: artists
                anchors.fill: parent
                visible: root.tab === 2
            }

            AdminUpload {
                id: upload
                anchors.fill: parent
                visible: root.tab === 3
                onShowConflicts: root.showConflicts()
            }

            AdminTeam {
                id: team
                anchors.fill: parent
                visible: root.tab === 4
            }
        }
    }
}
