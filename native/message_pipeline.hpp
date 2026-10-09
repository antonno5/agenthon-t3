// Three reusable column buffers: producer + at most two queued/writing blocks.
// Only the worker calls writer callbacks; no Arrow views survive a callback.
#pragma once
#include "engine.hpp"
#include <condition_variable>
#include <deque>
#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <utility>

namespace t3 {
inline void clear_messages(MessageColumns& m) {
  m.t_recv.clear(); m.t_send.clear(); m.latency.clear(); m.message_id.clear();
  m.order_id.clear(); m.causal_parent.clear(); m.t_send_null.clear();
  m.order_id_null.clear(); m.causal_null.clear(); m.src.clear(); m.dst.clear();
  m.msg_type.clear();
}
class MessagePipeline final : public MessageSink {
 public:
  using Write = std::function<void(const MessageColumns&, size_t)>;
  MessagePipeline(Write write, std::function<void()> close)
      : write_(std::move(write)), close_(std::move(close)) {
    free_.push_back(std::make_unique<MessageColumns>());
    free_.push_back(std::make_unique<MessageColumns>());
    worker_ = std::thread([this] { consume(); });
  }
  MessagePipeline(const MessagePipeline&) = delete;
  MessagePipeline& operator=(const MessagePipeline&) = delete;
  ~MessagePipeline() { cancel(); }

  void submit(MessageColumns& block) override {
    std::unique_lock<std::mutex> lock(mutex_);
    changed_.wait(lock, [this] { return error_ || stopped_ || !free_.empty(); });
    if (error_) std::rethrow_exception(error_);
    if (stopped_) throw std::runtime_error("message pipeline already stopped");
    auto buffer = std::move(free_.back());
    free_.pop_back();
    std::swap(*buffer, block);
    pending_.push_back(std::move(buffer));
    changed_.notify_all();
  }
  // No more blocks: the worker writes what is queued and closes the file. finish() waits for it;
  // calling close_async() first lets the caller do other work (the trace file) meanwhile.
  void close_async() {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      stopped_ = true;
    }
    changed_.notify_all();
  }
  void finish() {
    close_async();
    if (worker_.joinable()) worker_.join();
    if (error_) std::rethrow_exception(error_);
  }
  void cancel() noexcept {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      cancelled_ = stopped_ = true;
    }
    changed_.notify_all();
    if (worker_.joinable()) worker_.join();
  }
 private:
  void consume() noexcept {
    try {
      size_t offset = 0;
      for (;;) {
        std::unique_ptr<MessageColumns> block;
        {
          std::unique_lock<std::mutex> lock(mutex_);
          changed_.wait(lock, [this] { return stopped_ || !pending_.empty(); });
          if (cancelled_) return;
          if (pending_.empty()) break;
          block = std::move(pending_.front());
          pending_.pop_front();
        }
        write_(*block, offset);
        offset += block->t_recv.size();
        clear_messages(*block);
        {
          std::lock_guard<std::mutex> lock(mutex_);
          free_.push_back(std::move(block));
        }
        changed_.notify_all();
      }
      close_();
    } catch (...) {
      {
        std::lock_guard<std::mutex> lock(mutex_);
        error_ = std::current_exception();
        stopped_ = true;
      }
      changed_.notify_all();
    }
  }
  Write write_;
  std::function<void()> close_;
  std::mutex mutex_;
  std::condition_variable changed_;
  std::vector<std::unique_ptr<MessageColumns>> free_;
  std::deque<std::unique_ptr<MessageColumns>> pending_;
  bool stopped_ = false, cancelled_ = false;
  std::exception_ptr error_;
  std::thread worker_;
};
}  // namespace t3
