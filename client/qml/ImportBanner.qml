import QtQuick
import QtQuick.Layouts
import Wavelane

/*! Progress of a folder import, shown under the collection's tabs. */
Rectangle {
    id: root

    signal showConflicts()

    readonly property var job: library.importJob
    readonly property bool present: Object.keys(job).length > 0
    readonly property string state: present ? job.state : ""
    readonly property bool active: library.importActive

    visible: present
    implicitHeight: present ? 76 : 0
    color: Theme.panel

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.border
    }

    readonly property string headline: {
        if (!present)
            return ""
        switch (state) {
        case "scanning":  return qsTr("Ищем аудиофайлы…")
        case "running":   return qsTr("Импорт · %1 из %2").arg(job.processed).arg(job.total)
        case "cancelled": return qsTr("Импорт остановлен · %1 из %2").arg(job.processed).arg(job.total)
        case "failed":    return qsTr("Импорт прерван ошибкой")
        default:          return qsTr("Импорт завершён · %1 файлов").arg(job.total)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.topMargin: 10
        anchors.bottomMargin: 10
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Mono {
                text: root.headline
                color: Theme.text
                font.weight: Font.DemiBold
            }

            Mono {
                Layout.fillWidth: true
                text: root.active ? (root.job.current || "") : (root.job.path || "")
                font.capitalization: Font.MixedCase
                font.letterSpacing: 0.2
                color: Theme.faint
            }

            FlatButton {
                visible: root.active
                implicitHeight: 24
                text: qsTr("Остановить")
                onClicked: library.cancelImport()
            }
            FlatButton {
                visible: !root.active && library.conflicts.length > 0
                implicitHeight: 24
                text: qsTr("Конфликты: %1").arg(library.conflicts.length)
                onClicked: root.showConflicts()
            }
            FlatButton {
                visible: !root.active
                implicitHeight: 24
                text: qsTr("Закрыть")
                onClicked: library.dismissImport()
            }
        }

        // progress bar; indeterminate shimmer while the folder is still being scanned
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 3
            color: Theme.borderStrong
            clip: true

            Rectangle {
                visible: root.state !== "scanning"
                width: parent.width * library.importFraction
                height: parent.height
                color: root.state === "failed" ? Theme.negative : Theme.accent

                Behavior on width { NumberAnimation { duration: 300 } }
            }

            Rectangle {
                id: shimmer
                visible: root.state === "scanning"
                width: parent.width * 0.25
                height: parent.height
                color: Theme.accent

                SequentialAnimation on x {
                    running: shimmer.visible
                    loops: Animation.Infinite
                    NumberAnimation { from: -shimmer.width; to: shimmer.parent.width; duration: 1100 }
                }
            }
        }

        Row {
            spacing: 22

            Mono { text: qsTr("Добавлено ") + (root.present ? root.job.imported : 0); color: Theme.positive }
            Mono { text: qsTr("Дубликатов ") + (root.present ? root.job.duplicates : 0); color: Theme.muted }
            Mono {
                text: qsTr("Конфликтов ") + (root.present ? root.job.conflicts : 0)
                color: root.present && root.job.conflicts > 0 ? Theme.warning : Theme.muted
            }
            Mono {
                text: qsTr("Ошибок ") + (root.present ? root.job.failed : 0)
                color: root.present && root.job.failed > 0 ? Theme.negative : Theme.muted
            }
        }
    }
}
