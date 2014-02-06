var MessageBus = Class.create({
  initialize: function() {
    this.callCounter = 0;
    this.callbacks = {};
    this._reconnectTimeoutId = null;
    this._helloTimeoutId = null;
  },

  connect: function() {
    var protocol = 'ws:';
    if (window.location.protocol === 'https:') {
      protocol = 'wss:';
    }

    var url = protocol + '//' + window.location.hostname + ':' + window.location.port + '/wsapi';
    console.log('connecting to', url);
    this.ws = new WebSocket(url);
    this.ws.onmessage = $.proxy(this, 'onMessage');
    this.ws.onclose = $.proxy(this, 'onClose');
    this.ws.onopen = $.proxy(this, 'onOpen');
    this.ws.onerror = $.proxy(this, 'onError');
  },
  
  onOpen: function() {
    console.log('onOpen', arguments);
    $(document).trigger('connected');
    this._reconnectTimeoutId = null;
    this.sendHello();
  },
  
  // keep sending hello every so often to detech if the connection dropped
  sendHello: function() {
    this.send('hello');
    this._helloTimeoutId = this.sendHello.bind(this).delay(5);
  },
  
  onClose: function() {
    console.log('onClose', this, arguments);
    $(document).trigger('disconnected');
    this._reconnectTimeoutId = this.connect.bind(this).delay(1);
    if (this._helloTimeoutId) {
      window.clearTimeout(this._helloTimeoutId);
      this._helloTimeoutId = null;
    }
  },
  
  onError: function() {
    console.log('onError', arguments);
  },
  
  cancelConnect: function() {
    if (this._reconnectTimeoutId) {
      window.clearTimeout(this._reconnectTimeoutId);
    }
    this._reconnectTimeoutId = null;
  },
  
  
  onMessage: function(evt) {
    var jsonData
    try {
      jsonData = JSON.parse(evt.data);
    } catch(e) {
      console.log('error while parsing', evt.data);
    }
      
    var action = jsonData.shift();
    if (!action.endsWith('progress')) {
      console.log('event', action, jsonData);
    }
    if (action == 'return' || action == 'exception') {
      var callId = jsonData.shift();
      if (!this.callbacks.hasOwnProperty(callId)) {
        console.error('got return for a call I do know about', callId, Object.keys(this.callbacks));
        return;
      }
      console.log('callback for', callId, this.callbacks[callId]);
      this.callbacks[callId].apply(this, jsonData);
      delete this.callbacks[callId];
      return;
    }
    $(document).trigger(action, jsonData);
  },
  
  send: function(/* vararg */) {
    var dataStr = JSON.stringify([].splice.call(arguments,0));
    console.log('sending', dataStr);
    this.ws.send(dataStr);
  }, 
  
  call: function(name, args, callback) {
    var data = ['call', ++this.callCounter, name, args];
    this.send.apply(this, data);
    if (!callback) {
      callback = function() {};
    }
    this.callbacks[this.callCounter] = callback;
    return this.callCounter;
  }
});
