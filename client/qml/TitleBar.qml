import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wavelane

/*!
    The strip along the top of the window, which is also its title bar.

    It carries the current page's heading and that page's controls, so they sit
    on the same line as the window buttons instead of taking a row of their own
    below. Signed out it shows the brand instead.
*/
Rectangle {
    id: root

    required property var window
    property string page: "wave"
    property bool detailOpen: true
    //! The collection's active tab, which decides whether the detail toggle applies.
    property int collectionTab: 0

    signal toggleDetail()
    signal openUpload()
    signal openImport()
    signal showConflicts()

    readonly property bool signedIn: auth.signedIn
    readonly property bool maximized: window.visibility === Window.Maximized
    readonly property bool onWave: signedIn && page === "wave"
    readonly property bool onSearch: signedIn && page === "search"
    readonly property bool onCollection: signedIn && page === "collection"

    // The numbers follow the order of the sidebar.
    readonly property string pageNumber: page === "search" ? "01" : page === "wave" ? "02" : "03"
    readonly property string pageTitle: page === "search" ? qsTr("Поиск")
                                        : page === "wave" ? qsTr("Моя волна")
                                        : qsTr("Коллекция")

    color: signedIn ? "transparent" : Theme.bar

    readonly property var characterOptions: [
        { value: "any",        label: qsTr("Любой") },
        { value: "favourite",  label: qsTr("Любимое") },
        { value: "unfamiliar", label: qsTr("Новое") },
        { value: "popular",    label: qsTr("Хиты") }
    ]
    readonly property var moodOptions: [
        { value: "any",       label: qsTr("Любое настроение") },
        { value: "energetic", label: qsTr("Бодрое") },
        { value: "party",     label: qsTr("Танцевальное") },
        { value: "chill",     label: qsTr("Спокойное") },
        { value: "calm",      label: qsTr("Тихое") },
        { value: "focus",     label: qsTr("Для сосредоточения") },
        { value: "sad",       label: qsTr("Грустное") }
    ]
    readonly property var languageOptions: [
        { value: "any",          label: qsTr("Любой язык") },
        { value: "russian",      label: qsTr("Русский") },
        { value: "foreign",      label: qsTr("Иностранный") },
        { value: "instrumental", label: qsTr("Без слов") }
    ]
    readonly property var diversityOptions: [
        { value: "0.1", label: qsTr("Разнообразие 10%") },
        { value: "0.3", label: qsTr("Разнообразие 30%") },
        { value: "0.6", label: qsTr("Разнообразие 60%") },
        { value: "0.9", label: qsTr("Разнообразие 90%") }
    ]

    //! The stored diversity is a free number; show the nearest preset.
    function nearestDiversity() {
        let best = diversityOptions[0].value
        let distance = 10
        for (let i = 0; i < diversityOptions.length; ++i) {
            const gap = Math.abs(parseFloat(diversityOptions[i].value) - wave.diversity)
            if (gap < distance) {
                distance = gap
                best = diversityOptions[i].value
            }
        }
        return best
    }

    // --- drag the window by any empty part of the bar -----------------------
    Item {
        anchors.fill: parent

        DragHandler {
            target: null
            onActiveChanged: if (active) root.window.startSystemMove()
        }
        TapHandler {
            onDoubleTapped: root.maximized ? root.window.showNormal()
                                           : root.window.showMaximized()
        }
    }

    // A line under the bar, except on the wave page where the glow runs behind it.
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.border
        visible: !root.onWave
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // --- brand, only before sign-in ---
        Row {
            visible: !root.signedIn
            Layout.leftMargin: 14
            spacing: 10

            Logo {
                size: 24
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: "Wavelane"
                color: Theme.text
                font.family: Theme.sans
                font.pixelSize: 16
                font.weight: Font.Bold
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // --- the page's heading: number badge and name ---
        Row {
            visible: root.signedIn
            Layout.leftMargin: 14
            Layout.alignment: Qt.AlignVCenter
            spacing: 10

            Rectangle {
                width: 18
                height: 16
                color: Theme.accent
                anchors.verticalCenter: parent.verticalCenter

                Mono {
                    anchors.centerIn: parent
                    text: root.pageNumber
                    color: "white"
                    font.pixelSize: 10
                    font.weight: Font.Bold
                }
            }
            Mono {
                text: root.pageTitle
                color: Theme.text
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }

        // --- Поиск ---
        BusyIndicator {
            visible: root.onSearch && library.searching
            running: visible
            implicitWidth: 18
            implicitHeight: 18
            Layout.alignment: Qt.AlignVCenter
        }
        IconButton {
            visible: root.onSearch
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: 8
            glyph: Theme.iPanel
            active: root.detailOpen
            activeColor: Theme.accentText
            tooltip: qsTr("Панель деталей · Ctrl+B")
            onClicked: root.toggleDetail()
        }

        // --- Коллекция ---
        Mono {
            visible: root.onCollection && library.uploadStatus !== ""
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: 12
            text: library.uploadStatus
            font.capitalization: Font.MixedCase
            color: library.uploading ? Theme.accentText : Theme.muted
        }
        FlatButton {
            visible: root.onCollection && auth.isAdmin && library.conflicts.length > 0
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: 6
            implicitHeight: 26
            text: qsTr("Конфликты: %1").arg(library.conflicts.length)
            onClicked: root.showConflicts()
        }
        // Adding music is for administrators; everyone else just listens.
        FlatButton {
            visible: root.onCollection && auth.isAdmin
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: 6
            implicitHeight: 26
            glyph: Theme.iFolder
            text: qsTr("Импорт папки")
            enabledWhen: !library.importActive
            onClicked: root.openImport()
        }
        FlatButton {
            visible: root.onCollection && auth.isAdmin
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: 6
            implicitHeight: 26
            glyph: Theme.iAdd
            text: library.uploading ? qsTr("Загрузка…") : qsTr("Загрузить файлы")
            enabledWhen: !library.uploading
            onClicked: root.openUpload()
        }
        IconButton {
            visible: root.onCollection && root.collectionTab < 3
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: 8
            glyph: Theme.iPanel
            active: root.detailOpen
            activeColor: Theme.accentText
            tooltip: qsTr("Панель деталей · Ctrl+B")
            onClicked: root.toggleDetail()
        }

        // --- Моя волна: the dials ---
        Segmented {
            visible: root.onWave
            Layout.alignment: Qt.AlignVCenter
            options: root.characterOptions
            current: wave.character
            onPicked: function(value) { wave.setCharacter(value) }
        }
        FlatCombo {
            visible: root.onWave
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 8
            implicitWidth: 176
            options: root.moodOptions
            current: wave.mood
            onPicked: function(value) { wave.setMood(value) }
        }
        FlatCombo {
            visible: root.onWave
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 6
            implicitWidth: 122
            options: root.languageOptions
            current: wave.language
            onPicked: function(value) { wave.setLanguage(value) }
        }
        FlatCombo {
            visible: root.onWave
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: 6
            Layout.rightMargin: 14
            implicitWidth: 180
            options: root.diversityOptions
            current: root.nearestDiversity()
            onPicked: function(value) { wave.setDiversity(parseFloat(value)) }
        }

        // --- window controls ---
        WindowButton {
            Layout.alignment: Qt.AlignTop
            glyph: Theme.iMinimize
            onClicked: root.window.showMinimized()
        }
        WindowButton {
            Layout.alignment: Qt.AlignTop
            glyph: root.maximized ? Theme.iRestore : Theme.iMaximize
            onClicked: root.maximized ? root.window.showNormal() : root.window.showMaximized()
        }
        WindowButton {
            Layout.alignment: Qt.AlignTop
            glyph: Theme.iWinClose
            danger: true
            onClicked: root.window.close()
        }
    }
}
