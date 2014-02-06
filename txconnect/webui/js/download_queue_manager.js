var DownloadQueueManager = Class.create({
  initialize: function() {
    $('#tabs-start a#download-queue').click($.proxy(this, 'onDownloadQueueClick'));
  },

  onDownloadQueueClick: function(evt) {
    if ($('.download-queue-panel:visible').size() != 0) {
      $tabs.tabs('select', $('.download-queue-panel').attr('id'));
      return;
    }
    this.newTab();
  },
  
  newTab: function() {
    var panelId = '#tabs-'+(++$tab_counter);
    $tabs.tabs('add', panelId, 'Download Queue');
    var tmp = $('#download-queue-panel-template').clone();
    tmp.attr('id', null);
    tmp.appendTo(panelId);
    $(panelId).data('controller', new DownloadQueuePanel(panelId));
    $tabs.tabs('select', panelId);
  },
  
});


var DownloadQueuePanel = Class.create({
  initialize: function(selector) {
    this.selector = selector;

    this.files = $('table', selector).dataTable({
      'bPaginate': false,
      'bLengthChange': false,
      'bFilter': true,
      'bInfo': false,
      'bAutoWidth': true,
      'bJQueryUI': true,
      'bFilter': false
    });
    this.refresh();
  },
  
  refresh: function() {
    tx.messageBus.call('download:outpaths', [], function(outpaths) {
      $(".directories-inner", this.selector).tree({
        callback: {
          onselect: $.proxy(this, 'onDirectorySelect') 
        },
        data: {
          type: 'json',
          opts: {
            static: this.adaptData(outpaths)
          }
        }
      });
      $.tree.focused().open_all();
    }.bind(this));
  },
  
  adaptData: function(tree) {
    return Object.keys(tree).collect(function(key) {
      return {data: key, children: this.adaptData(tree[key])};
    }.bind(this));
  },

  onDirectorySelect: function(node, tree) {
    this.files.fnClearTable();
    var nodes = [];
    var currentNode = node;
    while (currentNode != -1) {
      nodes.unshift(tree.get_text(currentNode));
      currentNode = tree.parent(currentNode);
    };
    tx.messageBus.call('download:filesForOutpath', [nodes.join('/')], function(files) {
      files.each(function(file) {
        var row = [
          file.filename,
          HumanReadable.filesize(file.size) || 0,
          file.sources,
          file.tth
        ];
        
        this.files.fnAddData( row );
      }, this);
    }.bind(this));
  }
  
});
