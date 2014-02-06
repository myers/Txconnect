var SearchManager = Class.create({
  initialize: function() {
    $('form#start_search').submit($.proxy(this, 'onStartSearch'));
    $('#tabs-start a#advanced-search').click($.proxy(this, 'onAdvancedSearchClick'));
    $(document).bind('search:result', $.proxy(this, 'onSearchResult'));

    // used to route search result events to the right panel
    this.searches = {};
  },

  onStartSearch: function(evt) {
    var termInput = $('input[name=term]', evt.target);
    var term = termInput.val();
    this.newTab(term);
    termInput.val('');
    return false;
  },
  onAdvancedSearchClick: function(evt) {
    this.newTab();
    return false;
  },

  search: function(panel, term, options) {
    if (panel.searchId) {
      console.log('deleting searchId', panel.searchId);
      tx.messageBus.call('search:delete', [panel.searchId]);
      delete this.searches[panel.searchId];
    }
    tx.messageBus.call('search', [term, options], function(results) {
      console.log('searchId is', results[0]);
      console.log('wait times are', results[1]);
      panel.notifyWaitTimes(results[1]);
      panel.searchId = results[0];
      this.searches[results[0]] = panel
    }.bind(this));
  },
  
  newTab: function(term) {
    var panelId = '#tabs-'+(++$tab_counter);
    $tabs.tabs('add', panelId, 'Search');
    var tmp = $('#search-panel-template').clone();
    tmp.attr('id', null);
    tmp.appendTo(panelId);
    $(panelId).data('controller', new SearchPanel(this, panelId, term));
    $tabs.tabs('select', panelId);
    tmp.find('input[name=term]').focus();
    return panelId;
  },
  
  onSearchResult: function(evt, searchId) {
    console.log('manager onSearchResult', arguments);
    if (!this.searches.hasOwnProperty(searchId)) return;
    this.searches[searchId].onSearchResult.apply(this.searches[searchId], $A(arguments).slice(2));
  },
});

var SearchPanel = Class.create({
  initialize: function(manager, selector, term) {
    this.searchId = null;
    this.manager = manager;
    this.selector = selector;
    $(selector).find('form').submit($.proxy(this, 'onSearchSubmit'));
    var results = this.results = $(selector).find('table').dataTable({
      'bPaginate': false,
      'bLengthChange': false,
      'bFilter': true,
      'bInfo': false,
      'bAutoWidth': true,
      'bJQueryUI': true,
      'bFilter': false
    });
    //new FixedHeader(results);

    $(selector).find('tbody').click(function(event) {
      $(results.fnSettings().aoData).each(function (){
        $(this.nTr).removeClass('row_selected');
      });
      $(event.target).parent('tr').addClass('row_selected');
    });
                      
    $(selector).find('table tbody tr').live('dblclick', $.proxy(this, 'onDoubleClick'));
    if (term) {
      $(selector).find('input[name=term]').val(term);
      $(selector).find('form.file_search').submit();
    }
  },
  
  onSearchResult: function(result) {
    $(this.selector).find('.wait_time').text('');
    console.log('result', result);
    if (result.type == 'directory' && result.tth) {
      console.error('directories cannot have tths');
      result.tth = '';
    }
    var row = [
      //File
      result.filepath.split('\\').last(),
      //Hits
      '',
      //User
      result.nick,
      //Type
      result.type == 'file' ? result.filepath.split('.').last() : result.type,
      //Size  TODO port humanreadble
      result.size ? result.size : '',
      //Path
      result.filepath,
      //Slots
      result.slots.join('/'),
      //Connection
      '',
      //Hub
      '', // TODOresult.hubname,
      //Exact Size
      result.size ? result.size : '',
      //TTH Root
      result.tth ? result.tth : ''
    ];
    console.log('row', row);
    
    var indexes = this.results.fnAddData( row );
    $(this.results.fnGetNodes()[indexes[0]]).data('result', result);
  },

  onDoubleClick: function(evt) {
    console.log('dbclick', evt);
    var result = $(evt.currentTarget).data('result');
    console.log('downloading', result);
    tx.messageBus.call('download', [result.peer, result.filepath, result.type, result.tth, result.size]);
  },
  
  onSearchSubmit: function(evt) {
    evt.preventDefault();
    try {
      var options = $(evt.target).serializeArray().inject({}, function(acc, val) {
        acc[val.name] = val.value;
        return acc;
      });
      var term = options.term;
      delete options.term;
      options.filetype = parseInt(options.filetype);
      this.manager.search(this, term, options);
      this.results.fnClearTable();
    } catch(e) {
      console.error(e);
    }
    return false;
  },

  notifyWaitTimes: function(times) {
    $(this.selector).find('.wait_time').text('waiting about ' + Math.round(Math.max(times)) + ' seconds for results');
  },
});
