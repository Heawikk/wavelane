import QtQuick
import QtQuick.Layouts
import Wavelane

/*!
    A track table with the detail panel beside it, and the selection logic
    that ties them together. Search and the collection both use it.
*/
RowLayout {
    id: root

    //! A TrackListModel.
    property var model: null
    property string context: "search"
    property bool playable: true
    property string emptyText: ""
    property bool detailOpen: true
    property string selectedId: ""

    spacing: 0

    // Look the selected track up wherever it lives. The revisions are read
    // only to make the binding re-run when any of those lists changes.
    readonly property var detailTrack: {
        const dependencies = (root.model ? root.model.revision : 0) + wave.history.revision
                             + wave.queue.revision + library.liked.revision
                             + library.catalogue.revision + library.searchResults.revision
        const playing = player.hasTrack ? player.currentTrack : null

        if (selectedId === "")
            return playing

        const models = [root.model, wave.history, wave.queue, library.catalogue,
                        library.liked, library.searchResults]
        for (let i = 0; i < models.length; ++i) {
            if (!models[i])
                continue
            const row = models[i].indexOfId(selectedId)
            if (row >= 0)
                return models[i].get(row)
        }
        // Selected something that is no longer in any list: show what is playing.
        return playing
    }

    onDetailTrackChanged: if (detailTrack && detailTrack.id) library.loadDetail(detailTrack.id)

    // a different list means the old selection no longer applies
    onModelChanged: selectedId = ""

    function playSelected() {
        if (!root.playable || !root.model)
            return
        const row = root.model.indexOfId(root.selectedId)
        if (row >= 0)
            library.playFrom(root.model, row, root.context)
    }

    function focusTable() { table.forceActiveFocus() }

    TrackTable {
        id: table
        Layout.fillWidth: true
        Layout.fillHeight: true

        model: root.model
        context: root.context
        playable: root.playable
        emptyText: root.emptyText
        selectedId: root.selectedId
        onTrackSelected: function(trackId) { root.selectedId = trackId }
    }

    Rectangle {
        Layout.preferredWidth: 1
        Layout.fillHeight: true
        color: Theme.border
        visible: root.detailOpen
    }

    DetailPanel {
        Layout.preferredWidth: Theme.detailWidth
        Layout.fillHeight: true
        visible: root.detailOpen
        track: root.detailTrack
        canPlay: root.playable
        onPlayRequested: root.playSelected()
    }
}
