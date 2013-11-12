"""
txcons.py

Transaction Constructors for the blockchain.
"""

from coloredcoinlib import txspec
from pycoin import encoding
from pycoin.tx import UnsignedTx, SecretExponentSolver
from binascii import hexlify

import io


class BasicTxSpec(object):
    """Represents a really simple colored coin transaction.
    Specifically, this particular transaction class has not been
    constructed, composed or signed. Those are done in other classes.
    """
    def __init__(self, model):
        """Create a BasicTxSpec that has a wallet_model <model>
        """
        self.model = model
        self.targets = []

    def add_target(self, target_addr, asset, value):
        """Add a receiving address <target_addr> for the transaction
        that will send color <asset> an amount <value>
        in Satoshi worth of colored coins.
        """
        self.targets.append((target_addr, asset, value))

    def is_monoasset(self):
        """Returns a boolean representing if the transaction is sending
        at most 1 color. Note that this method requires at least
        1 target to be defined or will raise an Exception.
        Use add_target to add a target address first.
        """
        if not self.targets:
            raise Exception('basic txs is empty')
        asset = self.targets[0][1]
        for target in self.targets:
            if target[1] != asset:
                return False
        return True

    def is_monocolor(self):
        """Returns a boolean representing if the transaction sends
        coins of exactly 1 color.
        """
        if not self.is_monoasset():
            return False
        asset = self.targets[0][1]
        return len(asset.get_color_set().color_id_set) == 1

    def is_uncolored(self):
        """Returns a boolean representing if the transaction is
        simply a transferring of uncolored bitcoins and not any
        colored coins.
        """
        if not self.is_monoasset():
            return False
        asset = self.targets[0][1]
        return asset.get_color_list().color_id_set == set([0])


class SimpleOperationalTxSpec(txspec.OperationalTxSpec):
    """Subclass of OperationalTxSpec which uses wallet model.
    Represents a transaction that's ready to be composed
    and then signed. The parent is an abstract class.
    """
    def __init__(self, model, asset):
        """Initialize a transaction that uses a wallet model
        <model> and transfers asset/color <asset>.
        """
        super(SimpleOperationalTxSpec, self).__init__()
        self.model = model
        self.targets = []
        self.asset = asset

    def add_target(self, target_addr, color_id, colorvalue):
        """Add a receiving address <target_addr> for the transaction
        that will send color <color_id> an amount <colorvalue>
        in Satoshi worth of colored coins.
        """
        self.targets.append((target_addr, color_id, colorvalue))

    def get_targets(self):
        """Get a list of (receiving address, color_id, colorvalue)
        triplets representing all the targets for this tx.
        """
        return self.targets

    def get_change_addr(self, color_id):
        """Get an address associated with color <color_id>
        that is in the current wallet for receiving change.
        """
        from wallet_model import ColorSet
        wam = self.model.get_address_manager()
        color_set = None
        if color_id == 0:
            color_set = ColorSet.from_color_ids(self.model, [0])
        elif self.asset.get_color_set().has_color_id(color_id):
            color_set = self.asset.get_color_set()
        if color_set is None:
            raise Exception('wrong color id')
        aw = wam.get_change_address(color_set)
        return aw.get_address()

    def select_coins(self, color_id, value):
        """Return a list of utxos and sum that corresponds to
        the colored coins identified by <color_id> of amount <value>
        in Satoshi that be spending from our wallet.
        """
        if not ((color_id == 0)
                or self.asset.get_color_set().has_color_id(color_id)):
            raise Exception("wrong color id requested")
        color_id_set = set([color_id])
        cq = self.model.make_coin_query({"color_id_set": color_id_set})
        utxo_list = cq.get_result()

        ssum = 0
        selection = []
        if value == 0:
            raise Exception('cannot select 0 coins')
        for utxo in utxo_list:
            ssum += utxo.value
            selection.append(utxo)
            if ssum >= value:
                return selection, ssum
        raise Exception('not enough coins to reach the target')

    def get_required_fee(self, tx_size):
        """Given a transaction that is of size <tx_size>,
        return the transaction fee in Satoshi that needs to be
        paid out to miners.
        """
        return 10000  # TODO


class SignedTxSpec(object):
    """Represents a transaction that's been signed and ready
    to be transmitted.
    """
    def __init__(self, model, composed_tx_spec, testnet):
        """Create a signed transaction with wallet model <model>
        and a composed transaction <composed_tx_spec>. <testnet>
        is a boolean representing whether this is a testnet address.
        """
        self.model = model
        self.testnet = testnet
        self.composed_tx_spec = composed_tx_spec
        self.construct_tx()

    def construct_tx(self):
        """Adds the signed transaction data to the transaction. This is
        entirely derived from the composed_tx_spec property
        and sets the tx_data property.
        """
        # get the inputs and outputs
        input_utxos = [txin.utxo for txin in self.composed_tx_spec.get_txins()]
        inputs = [utxo.get_pycoin_coin_source() for utxos in input_utxos]
        outputs = [(txout.value, txout.target_addr)
                   for txout in self.composed_tx_spec.get_txouts()]
        # sign the transaction using the address's private key
        secret_exponents = [
            encoding.wif_to_tuple_of_secret_exponent_compressed(
                utxo.address_rec.address.privkey, is_test=self.testnet)[0]
            for utxo in input_utxos]
        unsigned_tx = UnsignedTx.standard_tx(
            inputs, outputs, is_test=self.testnet)
        solver = SecretExponentSolver(secret_exponents)
        new_tx = unsigned_tx.sign(solver)
        s = io.BytesIO()
        new_tx.stream(s)
        self.tx_data = s.getvalue()

    def get_tx_data(self):
        """Returns the signed transaction data.
        """
        return self.tx_data

    def get_hex_tx_data(self):
        """Returns the hex version of the signed transaction data.
        """
        return hexlify(self.tx_data).decode("utf8")


class TransactionSpecTransformer(object):
    """An object that can transform one type of transaction into another.
    Essentially has the ability to take a transaction, compose it
    and sign it by returning the appropriate objects.

    The general flow of transaction types is this:
    BasicTxSpec -> SimpleOperationalTxSpec -> ComposedTxSpec -> SignedTxSpec
    "basic"     -> "operational"           -> "composed"     -> "signed"
    """

    def __init__(self, model, config):
        """Create a transaction transformer object for wallet_model <model>
        and a wallet configuration <config>
        """
        self.model = model
        self.testnet = config.get('testnet', False)

    def classify_tx_spec(self, tx_spec):
        """For a transaction <tx_spec>, returns a string that represents
        the type of transaction (basic, operational, composed, signed)
        that it is.
        """
        if isinstance(tx_spec, BasicTxSpec):
            return 'basic'
        elif isinstance(tx_spec, txspec.OperationalTxSpec):
            return 'operational'
        elif isinstance(tx_spec, txspec.ComposedTxSpec):
            return 'composed'
        elif isinstance(tx_spec, SignedTxSpec):
            return 'signed'
        else:
            return None

    def transform_basic(self, tx_spec, target_spec_kind):
        """Takes a basic transaction <tx_spec> and returns a transaction
        of type <target_spec_kind> which is one of (operational,
        composed, signed).
        """
        if target_spec_kind in ['operational', 'composed', 'signed']:
            if tx_spec.is_monoasset():
                asset = tx_spec.targets[0][1]
                operational_ts = asset.make_operational_tx_spec(tx_spec)
                return self.transform(operational_ts, target_spec_kind)
        raise Exception('do not know how to transform tx spec')

    def transform_operational(self, tx_spec, target_spec_kind):
        """Takes an operational transaction <tx_spec> and returns a
        transaction of type <target_spec_kind> which is one of
        (composed, signed).
        """
        if target_spec_kind in ['composed', 'signed']:
            if tx_spec.is_monocolor():
                color_id = tx_spec.get_targets()[0][1]
                if color_id == 0:
                    # compose a simple bitcoin transaction
                    targets = tx_spec.get_targets()
                    ttotal = sum([target[2] for target in targets])
                    fee = tx_spec.get_required_fee(500)
                    sel_utxos, sum_sel_coins = tx_spec.select_coins(
                        0, ttotal + fee)
                    txins = [txspec.ComposedTxSpec.TxIn(utxo)
                             for utxo in sel_utxos]
                    change = sum_sel_coins - ttotal - fee
                    txouts = [txspec.ComposedTxSpec.TxOut(target[2], target[0])
                              for target in targets]
                    # give ourselves the change
                    if change > 0:
                        outputs.append(
                            txspec.ComposedTxSpec.TxOut(
                                change, tx_spec.get_change_address(0)))
                    composed = txspec.ComposedTxSpec(txins, txouts)
                else:
                    color_def = self.model.get_color_map().get_color_def(
                        color_id)
                    composed = color_def.compose_tx_spec(tx_spec)
                return self.transform(composed, target_spec_kind)
        raise Exception('do not know how to transform tx spec')

    def transform_composed(self, tx_spec, target_spec_kind):
        """Takes a SimpleComposedTxSpec <tx_spec> and returns
        a signed transaction. For now, <target_spec_kind> must
        equal "signed" or will throw an exception.
        """
        if target_spec_kind in ['signed']:
            return SignedTxSpec(self.model, tx_spec, self.testnet)
        raise Exception('do not know how to transform tx spec')

    def transform_signed(self, tx_spec, target_spec_kind):
        """This method is not yet implemented.
        """
        raise Exception('do not know how to transform tx spec')

    def transform(self, tx_spec, target_spec_kind):
        """Transform a transaction <tx_spec> into another type
        of transaction defined by <target_spec_kind> and returns it.
        """
        spec_kind = self.classify_tx_spec(tx_spec)
        if spec_kind is None:
            raise Exception('spec kind is not recognized')
        if spec_kind == target_spec_kind:
            return tx_spec
        if spec_kind == 'basic':
            return self.transform_basic(tx_spec, target_spec_kind)
        elif spec_kind == 'operational':
            return self.transform_operational(tx_spec, target_spec_kind)
        elif spec_kind == 'composed':
            return self.transform_composed(tx_spec, target_spec_kind)
        elif spec_kind == 'signed':
            return self.transform_signed(tx_spec, target_spec_kind)
