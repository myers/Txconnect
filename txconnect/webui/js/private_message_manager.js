// TODO: peer status (offline, online)
var PrivateMessageManager = Class.create({
  initialize: function() {
    // k: peer "nick$hub.com", v: PrivateMessagePanel instance
    this.privateMessages = {};
    $(document).bind('hub:to', $.proxy(this, 'onHubTo'));
    $(document).bind('hub:sent_to', $.proxy(this, 'onHubSentTo'));
    $(document).bind('hub:private_message:open', $.proxy(this, 'onOpen'));
  },

  onOpen: function(evt, peer) {
    if (!this.privateMessages.hasOwnProperty(peer)) {
      this.newTab(peer);
    }
  },
  
  onHubTo: function(evt, peer) {
    if (!this.privateMessages.hasOwnProperty(peer)) {
      this.newTab(peer);
    }
    this.privateMessages[peer].onHubTo.apply(this.privateMessages[peer], $A(arguments).slice(1));
  },

  onHubSentTo: function(evt, peer, timestamp, msg, sentFrom) {
    if (!this.privateMessages.hasOwnProperty(peer)) {
      this.newTab(peer);
    }
    this.privateMessages[peer].onHubTo.apply(this.privateMessages[peer], [sentFrom, timestamp, msg]);
  },

  newTab: function(peer) {
    $tabs.tabs('add', '#tabs-'+(++$tab_counter), peer.split('$', 1)[0]);
    var tmp = $('#private-message-template').clone();
    tmp.attr('id', null);
    var panelId = '#tabs-' + $tab_counter;
    tmp.appendTo(panelId);
    this.privateMessages[peer] = new PrivateMessagePanel(panelId, peer);
    $(panelId).data('controller', this.privateMessages[peer]);
    $(panelId).data('manager', this);
    $tabs.tabs('select', $tab_counter-1);
  },

  onClose: function(panel) {
    console.log('onClose', panel);
    Object.keys(this.privateMessages).each(function(peer) {
      if (this.privateMessages[peer] == panel) {
        delete this.privateMessages[peer];
        return $break;
      }
    }.bind(this));
  },

});

var PrivateMessagePanel = Class.create({
  initialize: function(selector, peer) {
    this.tabId = selector;
    this.panel = $(selector);
    this.messages = this.panel.find('.messages');

    this.peer = peer;
    // k: peer nick, v: jquery of that peers row
    this.panel.find('.chat_form').submit($.proxy(this, 'onFormSubmit'));
    this.savedScrollTop = 0;
  },

  onFormSubmit: function(evt) {
    var input = this.panel.find('.chat_form_input');
    var message = input.val();
    if (message != '') {
      tx.messageBus.call('to', [this.peer, message]);
      input.val('');
    }
    return false;
  },
  
  onHubTo: function(nick, timestamp, msg) {
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
