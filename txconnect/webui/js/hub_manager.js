var HubManager = Class.create({
  initialize: function() {
    // k: hub id, v: HubPanel instance
    this.hubs = {};
    $(document).bind('hub:new', $.proxy(this, 'onHubNew'));
    $(document).bind('hub:name', $.proxy(this, 'onHubName'));
    $(document).bind('hub:global_to', $.proxy(this, 'onHubSpecificEvent'));
    $(document).bind('hub:chat', $.proxy(this, 'onHubSpecificEvent'));
    $(document).bind('hub:user:new', $.proxy(this, 'onHubSpecificEvent'));
    $(document).bind('hub:user:update', $.proxy(this, 'onHubSpecificEvent'));
    $(document).bind('hub:user:quit', $.proxy(this, 'onHubSpecificEvent'));
    $(document).bind('hub:status', $.proxy(this, 'onHubSpecificEvent'));
  },

  onHubNew: function(evt, hubId) {
    if (this.hubs.hasOwnProperty(hubId)) {
      return;
    }
    $tabs.tabs('add', '#tabs-'+(++$tab_counter), hubId.substr(0, 20));
    var tmp = $('#hub-panel-template').clone();
    tmp.attr('id', null);
    var panelId = '#tabs-' + $tab_counter;
    tmp.appendTo(panelId);
    this.hubs[hubId] = new HubPanel(panelId, hubId);
    $(panelId).data('controller', this.hubs[hubId]);
    $tabs.tabs('select', $tab_counter-1);
  },

  onHubName: function(evt, hubId, name) {
    $('a[href=' + this.hubs[hubId].tabId + ']').text(name.substr(0, 20));
  },
  
  onHubSpecificEvent: function(evt, hubId) {
    if (!this.hubs[hubId]) {
      console.error('cannot find hub', hubId);
      return;
    }
    var method = 'on' + evt.type.replace('hub:', '').replace(':', '-').replace('_', '-').capitalize().camelize();
    this.hubs[hubId][method].apply(this.hubs[hubId], $A(arguments).slice(2));
  },

});

var HubPanel = Class.create({
  initialize: function(selector, id) {
    this.tabId = selector;
    this.panel = $(selector);
    this.messages = this.panel.find('.messages');

    this.id = id;
    // k: peer nick, v: jquery of that peers row
    this.peers = {}

    this.userList = $(selector).find('table').dataTable({
      'bPaginate': false,
      'bLengthChange': false,
      'bFilter': true,
      'bInfo': false,
      'bAutoWidth': true,
      'bJQueryUI': true,
      'bFilter': false
    });
    $(selector).find('table').dblclick($.proxy(this, 'onNickClick'));
    $(document).bind('connected', $.proxy(this, 'onConnected'));
    
    this.panel.find('.chat_form').submit($.proxy(this, 'onFormSubmit'));
    this.savedScrollTop = 0;
  },
  onNickClick: function(evt) {
    var nick = evt.srcElement.innerText
    var peer = nick + '$' + this.id;
    $(document).trigger('hub:private_message:open', peer);
  },
  onConnected: function(evt) {
    this.userList.fnClearTable();
  },
  onFormSubmit: function(evt) {
    var input = this.panel.find('.chat_form_input');
    var message = input.val();
    if (message != '') {
      tx.messageBus.call('say', [this.id, message]);
      input.val('');
    }
    return false;
  },
  
  onUserNew: function(peer, op, info) {
    peer = peer.split('$');
    var indexes = this.userList.fnAddData( [peer[0]] );
    this.peers[peer[0]] = this.userList.fnGetNodes()[indexes[0]];
  },
  onUserQuit: function(peer) {
    peer = peer.split('$');
    this.userList.fnDeleteRow(this.peers[peer[0]]);
    delete this.peers[peer[0]];
  },
  onUserUpdate: function(peer) {
    //TODO
  },

  onChat: function(timestamp, msg) {
    this.onGlobalTo('hub', timestamp, msg);
  },
  
  onGlobalTo: function(nick, timestamp, msg) {
    var messageDate = Date.parseISO8601(timestamp);
    var prefix  = '';
    var tdClass = '';
    if (false) {
      prefix  = 'You:';
      tdClass = 'me';
    }
    else {
      prefix  = nick + ':';
      tdClass = 'nick';
    }
    var message = '<div class="message">';
    message += '<span class="timestamp">[ ' + messageDate.strftime('%H:%M') + ' ]</span> ';
    message += '<span class="' + tdClass + '">';
    message += prefix;
    message += '</span> ';
    message += '<tt>' + msg.escapeHTML().gsub(/\n/, '<br />\n').gsub(/\r/, '').gsub(/\t/, '&nbsp;&nbsp;&nbsp;&nbsp;') + '</tt>';
    message += '</div>';
    message = $(message);
    message.find('.timestamp').data('timestamp', messageDate);

    this.messages.append(message);
    this.messages.scrollTop(message.offset().top);
  },
  
  onStatus: function(status) {
    var message = $('<div class="status">').text(status + '...');
    this.messages.append(message);
    this.messages.scrollTop(message.offset().top);
  }, 

  scrollBottom: function() {
    return this.messages.scrollTop() + this.messages.height();
  },

  onShow: function() {
    if (this.savedScrollBottom == -1) {
      this.messages.scrollTop(this.messages[0].scrollHeight);
    } else {
      this.messages.scrollTop(this.savedScrollBottom-this.messages.height());
    }
  },
  
  onHide: function() {
    // remember the lowest point we where in the .messages
    var scrollHeight = this.messages[0].scrollHeight;
    if (scrollHeight == this.scrollBottom()) {
      this.savedScrollBottom = -1;
    } else {
      this.savedScrollBottom = this.scrollBottom();
    }
  }
});
