PeerPanel = Class.create({
  initialize: function() {
    $(document).bind('connected', $.proxy(this, 'onConnected'));
    $(document).bind('peer:new', $.proxy(this, 'onNew'));
    $(document).bind('peer:quit', $.proxy(this, 'onQuit'));
    $(document).bind('peer:upload:start', $.proxy(this, 'onUploadStart'));
    $(document).bind('peer:upload:progress', $.proxy(this, 'onUploadProgress'));
    $(document).bind('peer:upload:end', $.proxy(this, 'onUploadEnd'));
    $(document).bind('peer:download:start', $.proxy(this, 'onDownloadStart'));
    $(document).bind('peer:download:progress', $.proxy(this, 'onDownloadProgress'));
    $(document).bind('peer:download:end', $.proxy(this, 'onDownloadEnd'));
    this.peerTable = $('#peer-status').dataTable({
      'bPaginate': false,
      'bLengthChange': false,
      'bFilter': true,
      'bInfo': false,
      'bAutoWidth': false,
      'bJQueryUI': true,
      'bFilter': false,
      'aoColumns': [ 
        { 'sWidth': '20%' },
        null,
        null,
        null,
        null,
        null,
        null,
        null
      ]
    });
    //new FixedHeader(this.peerTable);
  },
  
  onConnected: function(evt) {
    this.peerTable.fnClearTable();
  },
  
  onNew: function(evt, peerId, nick, hubaddr) {
    $('#peer-status tbody').append('<tr id="peer_' + peerId +'"><td class="nick"><span class="direction ui-icon"></span>' + nick + '</td>' +
      '<td class="hub">' + hubaddr + '</td><td class="status">idle</td><td class="time-left">-</td>' +
      '<td class="speed">-</td><td class="filename">-</td><td class="size">-</td><td class="path">-</td>');


/*    this.peerTable.fnAddData([
     '<span class="direction ui-icon"></span>' + nick,
     hubaddr,
     'idle',
     '-',
     '-',
     '-',
     '-',
     '-'
    ]);
*/     
  },
  onQuit: function(evt, peerId) {
    $('#peer_' + peerId).remove();
  },
  onUploadStart: function(evt, peerId, filePath, bytesToSend, bytesUploaded, rate) {
    var domId = '#peer_' + peerId;
    $('.nick span.direction', domId).addClass('ui-icon-arrowthick-1-n');
    $('.status', domId).html('uploading ' + HumanReadable.percent(bytesUploaded, bytesToSend));
    $('.filename', domId).html(filePath);
  },
  onUploadProgress: function(evt, peerId, bytesTotal, bytesUploaded, rate) {
    var domId = '#peer_' + peerId;
    $('.status', domId).html('uploading ' + HumanReadable.percent(bytesUploaded, bytesTotal));
    $('.time-left', domId).html(HumanReadable.time((bytesTotal - bytesUploaded) / rate));
    $('.speed', domId).html(HumanReadable.filesize(rate) + '/s');
  },
  onUploadEnd: function(evt, peerId, bytesTotal, bytesUploaded, rate) {
    var domId = '#peer_' + peerId;
    $('.status', domId).html('idle');
    $('.speed', domId).html(HumanReadable.filesize(rate) + '/s');
  },
  onDownloadStart: function(evt, peerId, filePath, bytesTotal, bytesDownloaded, rate) {
    var domId = '#peer_' + peerId;
    $('.nick span.direction', domId).addClass('ui-icon-arrowthick-1-s');
    $('.status', domId).html('downloading ' + HumanReadable.percent(bytesDownloaded, bytesTotal));
    $('.filename', domId).html(filePath.substr(filePath.lastIndexOf('\\')+1));
    $('.path', domId).html(filePath.substr(0, filePath.lastIndexOf('\\')));
    $('.size', domId).html(HumanReadable.filesize(bytesTotal));
  },
  onDownloadProgress: function(evt, peerId, bytesTotal, bytesDownloaded, rate) {
    var domId = '#peer_' + peerId;
    $('.status', domId).html('downloading ' + HumanReadable.percent(bytesDownloaded, bytesTotal));
    $('.time-left', domId).html(HumanReadable.time((bytesTotal - bytesDownloaded) / rate));
    $('.speed', domId).html(HumanReadable.filesize(rate) + '/s');
    $('.size', domId).html(HumanReadable.filesize(bytesTotal));
  },
  onDownloadEnd: function(evt, peerId, bytesTotal, bytesUploaded, rate) {
    var domId = '#peer_' + peerId;
    $('.status', domId).html('idle');
    $('.speed', domId).html(HumanReadable.filesize(rate) + '/s');
  }
});
