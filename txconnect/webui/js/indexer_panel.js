IndexerPanel = Class.create({
  initialize: function() {
    $(document).bind('share_store:walking', $.proxy(this, 'onWalking'));
    $(document).bind('share_store:walking:done', $.proxy(this, 'onWalkingDone'));
    $(document).bind('share_store:hashing', $.proxy(this, 'onHashing'));
    $(document).bind('share_store:hashed', $.proxy(this, 'onHashed'));
    $(document).bind('share_store:indexer:finished', $.proxy(this, 'onFinished'));
    $(document).bind('share_store:size', $.proxy(this, 'onSize'));
    $(document).bind('connected', $.proxy(this, 'onFinished'));

    $('form#start_indexer').submit($.proxy(this, 'onIndexerStart'));
  },
  
  onIndexerStart: function(evt) {
    evt.preventDefault();
    tx.messageBus.call('indexer:start', []);
  },
  
  onWalking: function(evt, options) {
    $('#indexer-stats').show();
    $('form#start_indexer input').attr('disabled', 'disabled');
    $('#indexer-stats .currentDirectory').text(options.currentDirectory);
    $('#indexer-stats .fileCount').text(HumanReadable.number(options.fileCount));
    $('#indexer-stats .skipped').text(HumanReadable.number(options.skipped));
  },
  
  onWalkingDone: function(evt, options) {
    $('#indexer-stats').show();
    $('#indexer-stats .currentDirectory').html('<b>finished looking for files to hash</b>');
    $('#indexer-stats .fileCount').text(HumanReadable.number(options.fileCount));
  },
  
  onHashing: function(evt, options) {
    $('#indexer-stats').show();
    $('#indexer-stats .fileBeingHashed').text(options.fileBeingHashed);
    $('#indexer-stats .filesToBeHash').text(HumanReadable.number(options.filesToBeHash));
    $('#indexer-stats .sizeToBeHash').text(HumanReadable.filesize(options.sizeToBeHash));
  },
  
  onHashed: function(evt, options) {
    $('#indexer-stats').show();
    $('#indexer-stats .fileBeingHashed').text(options.fileBeingHashed);
    $('#indexer-stats .filesToBeHash').text(HumanReadable.number(options.filesToBeHash));
    $('#indexer-stats .sizeToBeHash').text(HumanReadable.filesize(options.sizeToBeHash));
    $('#indexer-stats .rate').text(HumanReadable.filesize(options.rate) + '/s');
    $('#indexer-stats .timeLeft').text(HumanReadable.time(options.sizeToBeHash / options.rate));
  },
  
  onSize: function(evt, options) {
    $('#indexer .count').text(HumanReadable.number(options.count));
    $('#indexer .size').text(HumanReadable.filesize(options.size));
  },
  
  onFinished: function(evt) {
    $('form#start_indexer input').removeAttr('disabled');
    $('#indexer-stats').hide();
  }
  
});
