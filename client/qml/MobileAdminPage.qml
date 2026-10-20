import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*! The administrator's menu on a phone: the numbers, every track, and adding music. */
Item {
    id: root

    property int tab: 0

    readonly property var tabs: [
        { value: "0", label: qsTr("Dashboard") },
        { value: "1", label: qsTr("Треки") },
        { value: "2", label: qsTr("Артисты") },
        { value: "3", label: qsTr("Загрузка") }
    ]

    function refresh() {
        if (tab === 0)
            dashboard.refresh()
        else if (tab === 1)
            library.loadCatalogue()
        else if (tab === 2)
            artists.refresh()
    }

    onTabChanged: refresh()

    TrackEditDialog { id: editor }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 56

            Segmented {
                anchors.fill: parent
                anchors.margins: 10
                anchors.topMargin: 12
                anchors.bottomMargin: 8
                stretch: true
                options: root.tabs
                current: String(root.tab)
                onPicked: function(value) { root.tab = parseInt(value) }
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
                compact: true
            }

            ColumnLayout {
                anchors.fill: parent
                visible: root.tab === 1
                spacing: 0

                SearchBox {
                    Layout.fillWidth: true
                    placeholder: qsTr("Найти трек, исполнителя или альбом")
                    onSearched: function(text) { library.searchCatalogue(text) }
                }

                MobileTrackList {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    model: library.catalogue
                    context: "catalogue"
                    editable: true
                    emptyText: qsTr("Ничего не найдено. Загрузить музыку можно на вкладке «Загрузка».")
                    onEndReached: library.loadMoreCatalogue()
                    onEditRequested: function(trackId) { editor.openFor(trackId) }
                }
            }

            AdminArtists {
                id: artists
                anchors.fill: parent
                visible: root.tab === 2
                compact: true
            }

            AdminUpload {
                anchors.fill: parent
                visible: root.tab === 3
                compact: true
            }
        }
    }
}
